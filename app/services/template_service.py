from __future__ import annotations

import json
import os
import re
from typing import Any


TEMPLATE_PATTERN = re.compile(r"{{\s*([^}]+?)\s*}}")


def resolve_path(context: dict[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return None
    return current


def render_template(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: render_template(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_template(item, context) for item in value]
    if not isinstance(value, str):
        return value

    exact_match = TEMPLATE_PATTERN.fullmatch(value.strip())
    if exact_match:
        return _resolve_template_token(exact_match.group(1), context)

    def replacer(match: re.Match[str]) -> str:
        resolved = _resolve_template_token(match.group(1), context)
        if resolved is None:
            return ""
        if isinstance(resolved, str):
            return resolved
        return json.dumps(resolved, ensure_ascii=True, separators=(",", ":"))

    return TEMPLATE_PATTERN.sub(replacer, value)


def _resolve_template_token(token: str, context: dict[str, Any]) -> Any:
    token = token.strip()
    if token.startswith("env."):
        return os.getenv(token.removeprefix("env."))
    return resolve_path(context, token)
