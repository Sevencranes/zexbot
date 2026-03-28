from __future__ import annotations

from typing import Any


def extract_plain_text(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts: list[str] = []
        for seg in message:
            if isinstance(seg, dict) and seg.get("type") == "text":
                data = seg.get("data") or {}
                parts.append(str(data.get("text", "")))
        return "".join(parts)
    return str(message)
