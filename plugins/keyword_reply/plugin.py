"""
关键词回复：支持 fuzzy（消息包含关键词）/ exact（整句与关键词一致，去首尾空白）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from zexbot.core.onebot_text import extract_plain_text

display_name = "关键词回复"
plugin_author = "Zex"
log = logging.getLogger("zexbot.plugin.keyword_reply")

_ROOT = Path(__file__).resolve().parent
_CONFIG_PATH = _ROOT / "config.json"
_cache: dict[str, Any] = {"mtime_ns": 0, "rules": []}


def _load_rules() -> list[dict[str, Any]]:
    global _cache
    if not _CONFIG_PATH.is_file():
        return []
    try:
        st = _CONFIG_PATH.stat()
        ns = st.st_mtime_ns
    except OSError:
        return list(_cache.get("rules", []))
    if _cache.get("mtime_ns") == ns:
        return list(_cache.get("rules", []))
    try:
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("keyword_reply 读取配置失败: %s", e)
        return list(_cache.get("rules", []))
    rules = raw.get("rules") if isinstance(raw, dict) else []
    if not isinstance(rules, list):
        rules = []
    _cache = {"mtime_ns": ns, "rules": rules}
    return rules


async def on_config_updated() -> None:
    global _cache
    _cache = {"mtime_ns": 0, "rules": []}


async def on_message(event: dict[str, Any], bot: Any) -> None:
    if not bot.connected:
        return
    msg = event.get("message")
    plain = extract_plain_text(msg).strip()
    if not plain:
        return

    rules = _load_rules()
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        kw = str(rule.get("keyword", "")).strip()
        if not kw:
            continue
        mode = str(rule.get("mode", "fuzzy"))
        reply = str(rule.get("reply", ""))
        hit = False
        if mode == "exact":
            if plain == kw:
                hit = True
        else:
            if kw in plain:
                hit = True
        if not hit:
            continue
        if event.get("message_type") == "group":
            gid = event.get("group_id")
            if gid is None:
                return
            await bot.call_api(
                "send_group_msg",
                {"group_id": int(gid), "message": reply},
            )
        elif event.get("message_type") == "private":
            uid = event.get("user_id")
            if uid is None:
                return
            await bot.call_api(
                "send_private_msg",
                {"user_id": int(uid), "message": reply},
            )
        log.info("keyword_reply 命中: %s", kw[:32])
        return
