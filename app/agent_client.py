from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import httpx

from app.config import AgentSettings, settings
from app.models import AgentDefinition, AgentResponse, AuthType
from app.services.template_service import render_template


logger = logging.getLogger("app.agent_client")


class AgentClientError(Exception):
    """Raised when an external agent call fails."""


class AgentClient:
    def __init__(
        self,
        client_factory: Callable[..., httpx.AsyncClient] | None = None,
    ) -> None:
        self._client_factory = client_factory or httpx.AsyncClient

    async def run_agent(
        self,
        agent: AgentSettings,
        task: str,
        user_id: str,
        agent_session_id: str | None = None,
    ) -> dict[str, Any]:
        if not agent.enabled or agent.endpoint is None:
            raise AgentClientError(f"{agent.name} is not configured.")

        last_error: Exception | None = None
        timeout = httpx.Timeout(agent.timeout_seconds)
        for attempt in range(1, agent.max_retries + 1):
            try:
                if agent.transport != "run":
                    raise AgentClientError(f"Unsupported transport '{agent.transport}' for {agent.name}.")
                return await self._run_transport(agent, task, user_id, agent_session_id, timeout)
            except AgentClientError as exc:
                last_error = exc
                if attempt == agent.max_retries:
                    break
                logger.warning(
                    json.dumps(
                        {
                            "event": "agent_retry",
                            "step_id": agent.step_id,
                            "attempt": attempt,
                            "reason": str(exc),
                        }
                    )
                )
                await asyncio.sleep(agent.backoff_base_seconds * (2 ** (attempt - 1)))

        if last_error is not None:
            raise last_error
        raise AgentClientError(f"{agent.name} request failed for an unknown reason.")

    async def run_registered_agent(
        self,
        agent: AgentDefinition,
        *,
        context: dict[str, Any],
        timeout_seconds: float = 180.0,
        max_retries: int = 3,
        backoff_base_seconds: float = 0.5,
    ) -> dict[str, Any]:
        if not agent.enabled:
            raise AgentClientError(f"{agent.name} is disabled.")

        last_error: Exception | None = None
        timeout = httpx.Timeout(timeout_seconds)
        method = agent.method.upper()

        for attempt in range(1, max_retries + 1):
            try:
                headers = self._build_registered_headers(agent, context)
                payload = render_template(agent.payload_template_json, context)
                response = await self._request(
                    method=method,
                    url=agent.endpoint_url,
                    payload=payload,
                    headers=headers,
                    timeout=timeout,
                    agent_name=agent.name,
                    timeout_seconds=timeout_seconds,
                )
                normalized = self._parse_json_response(response)
                mapped = self._apply_response_mapping(normalized, agent.response_mapping_json)
                return mapped
            except AgentClientError as exc:
                last_error = exc
                if attempt == max_retries:
                    break
                logger.warning(
                    json.dumps(
                        {
                            "event": "agent_retry",
                            "agent_id": agent.id,
                            "attempt": attempt,
                            "reason": str(exc),
                        }
                    )
                )
                await asyncio.sleep(backoff_base_seconds * (2 ** (attempt - 1)))

        if last_error is not None:
            raise last_error
        raise AgentClientError(f"{agent.name} request failed for an unknown reason.")

    async def _run_transport(
        self,
        agent: AgentSettings,
        task: str,
        user_id: str,
        agent_session_id: str | None,
        timeout: httpx.Timeout,
    ) -> dict[str, Any]:
        del user_id
        if not settings.daisynova_api_token:
            raise AgentClientError("DaisyNova API token is missing.")
        payload = {
            "task": task,
            "wait": True,
        }
        if agent_session_id:
            payload["session_id"] = agent_session_id
        response = await self._post(
            agent,
            payload=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.daisynova_api_token}",
            },
            timeout=timeout,
        )
        normalized = self._parse_json_response(response)
        return normalized

    async def _post(
        self,
        agent: AgentSettings,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: httpx.Timeout,
    ) -> httpx.Response:
        async with self._client_factory(timeout=timeout) as client:
            try:
                response = await client.post(agent.endpoint, json=payload, headers=headers)
                response.raise_for_status()
                return response
            except httpx.TimeoutException as exc:
                raise AgentClientError(
                    f"{agent.name} request timed out after {agent.timeout_seconds} seconds."
                ) from exc
            except httpx.HTTPError as exc:
                raise AgentClientError(f"{agent.name} request failed: {exc}") from exc

    async def _request(
        self,
        *,
        method: str,
        url: str,
        payload: dict[str, Any] | list[Any] | str | None,
        headers: dict[str, str],
        timeout: httpx.Timeout,
        agent_name: str,
        timeout_seconds: float,
    ) -> httpx.Response:
        async with self._client_factory(timeout=timeout) as client:
            try:
                response = await client.request(method, url, json=payload, headers=headers)
                response.raise_for_status()
                return response
            except httpx.TimeoutException as exc:
                raise AgentClientError(f"{agent_name} request timed out after {timeout_seconds} seconds.") from exc
            except httpx.HTTPError as exc:
                raise AgentClientError(f"{agent_name} request failed: {exc}") from exc

    def _parse_json_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            payload = {"text": response.text}

        normalized = self._normalize_payload(payload)
        normalized_dict = normalized.model_dump()
        discovered_session_id = self._extract_session_id(payload)
        normalized_dict = self._apply_error_summary_if_empty(normalized_dict)
        normalized_dict = self._collapse_duplicate_output_fields(normalized_dict)
        if discovered_session_id:
            normalized_dict["agent_session_id"] = discovered_session_id
        return normalized_dict

    def _build_registered_headers(self, agent: AgentDefinition, context: dict[str, Any]) -> dict[str, str]:
        headers = render_template(agent.headers_json, context)
        if not isinstance(headers, dict):
            raise AgentClientError(f"{agent.name} headers template must render to an object.")
        normalized_headers = {str(key): "" if value is None else str(value) for key, value in headers.items()}
        if agent.auth_type == AuthType.BEARER and not normalized_headers.get("Authorization"):
            token = settings.daisynova_api_token
            if not token:
                raise AgentClientError("DaisyNova API token is missing.")
            normalized_headers["Authorization"] = f"Bearer {token}"
        return normalized_headers

    def _apply_response_mapping(self, normalized: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
        if not mapping:
            return normalized
        mapped = dict(normalized)
        for target_key, expression in mapping.items():
            if not isinstance(expression, str):
                continue
            resolved = self._resolve_json_path(
                expression,
                {
                    "content": normalized.get("content"),
                    "text": normalized.get("text"),
                    "raw": normalized.get("raw"),
                    "result": normalized.get("content"),
                    "response": normalized,
                },
            )
            if resolved is not None:
                mapped[target_key] = resolved
        return mapped

    def _resolve_json_path(self, expression: str, context: dict[str, Any]) -> Any:
        if not expression.startswith("$."):
            return None
        parts = expression[2:].split(".")
        current: Any = context
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
                continue
            return None
        return current

    def _normalize_payload(self, payload: Any) -> AgentResponse:
        if isinstance(payload, dict):
            for key in ("output", "result", "data", "response", "content"):
                if key in payload:
                    value = payload[key]
                    return AgentResponse(content=value, text=self._extract_text(value), raw=payload)
            return AgentResponse(content=payload, text=self._extract_text(payload), raw=payload)
        if isinstance(payload, list):
            return AgentResponse(content=payload, text=self._extract_text(payload), raw=payload)
        return AgentResponse(content=payload, text=str(payload), raw=payload)

    def _apply_error_summary_if_empty(self, normalized: dict[str, Any]) -> dict[str, Any]:
        content = normalized.get("content")
        raw = normalized.get("raw")
        if content not in ({}, "{}", None):
            return normalized
        if not isinstance(raw, dict):
            return normalized
        error_summary = self._extract_error_summary_from_logs(raw.get("logs"))
        if not error_summary:
            return normalized
        normalized["content"] = error_summary
        normalized["text"] = error_summary
        normalized["error_summary"] = error_summary
        return normalized

    def _collapse_duplicate_output_fields(self, normalized: dict[str, Any]) -> dict[str, Any]:
        content = normalized.get("content")
        text = normalized.get("text")
        raw = normalized.get("raw")

        rendered_content = self._render_output(content)
        rendered_text = text.strip() if isinstance(text, str) else None

        if rendered_content is not None and rendered_text == rendered_content:
            normalized["text"] = None

        if not isinstance(raw, dict):
            return normalized

        duplicate_keys = ("output", "result", "data", "response", "content", "text", "message")
        cleaned_raw = dict(raw)
        for key in duplicate_keys:
            if key not in cleaned_raw:
                continue
            rendered_raw_value = self._render_output(cleaned_raw.get(key))
            if rendered_raw_value is None:
                continue
            if rendered_content is not None and rendered_raw_value == rendered_content:
                cleaned_raw.pop(key, None)
                continue
            if rendered_text is not None and rendered_raw_value == rendered_text:
                cleaned_raw.pop(key, None)
        normalized["raw"] = cleaned_raw
        return normalized

    def _extract_text(self, value: Any) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for key in ("text", "message", "summary"):
                item = value.get(key)
                if isinstance(item, str):
                    return item
        return None

    def _extract_session_id(self, payload: Any) -> str | None:
        if isinstance(payload, dict):
            for key in ("session_id", "sessionId", "chat_session_id"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
            for value in payload.values():
                nested = self._extract_session_id(value)
                if nested:
                    return nested
        if isinstance(payload, list):
            for item in payload:
                nested = self._extract_session_id(item)
                if nested:
                    return nested
        return None

    def _extract_error_summary_from_logs(self, logs: Any) -> str | None:
        if not isinstance(logs, list):
            return None
        messages: list[str] = []
        for entry in logs:
            if not isinstance(entry, dict):
                continue
            message = entry.get("message")
            result = entry.get("result")
            if isinstance(message, str) and ("error" in message.lower() or "failed" in message.lower()):
                messages.append(message)
            if isinstance(result, str) and ("error" in result.lower() or "failed" in result.lower()):
                messages.append(result)
        if not messages:
            return None
        return messages[0]

    def _render_output(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip()
        try:
            return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        except TypeError:
            return str(value).strip()
