"""
群管 + 娱乐：可配置命令词、超管 QQ、群内菜单；禁言/踢人/全员禁言/撤回（依赖协议端与机器人权限）。
"""

from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path
from typing import Any

from zexbot.core.onebot_text import extract_plain_text

display_name = "群管套件"
plugin_author = "Zex"
log = logging.getLogger("zexbot.plugin.group_suite")

_ROOT = Path(__file__).resolve().parent
_CONFIG_PATH = _ROOT / "config.json"
_cache: dict[str, Any] = {"mtime_ns": 0, "cfg": {}}


def _load_cfg() -> dict[str, Any]:
    global _cache
    if not _CONFIG_PATH.is_file():
        return {}
    try:
        st = _CONFIG_PATH.stat()
        ns = st.st_mtime_ns
    except OSError:
        return dict(_cache.get("cfg", {}))
    if _cache.get("mtime_ns") == ns:
        return dict(_cache.get("cfg", {}))
    try:
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("group_suite 读取配置失败: %s", e)
        return dict(_cache.get("cfg", {}))
    if not isinstance(raw, dict):
        raw = {}
    _cache = {"mtime_ns": ns, "cfg": raw}
    return raw


async def on_config_updated() -> None:
    global _cache
    _cache = {"mtime_ns": 0, "cfg": {}}


def _pick(cfg: dict[str, Any], zh: str, default: Any = None) -> Any:
    v = cfg.get(zh)
    return default if v is None else v


def _norm_words(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, list):
        out: list[str] = []
        for x in raw:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
        return out
    return []


def _extract_at_qq(message: Any) -> list[int]:
    if not isinstance(message, list):
        return []
    out: list[int] = []
    for seg in message:
        if not isinstance(seg, dict):
            continue
        if seg.get("type") != "at":
            continue
        data = seg.get("data") or {}
        qq = data.get("qq")
        if qq is None:
            continue
        try:
            out.append(int(qq))
        except (TypeError, ValueError):
            pass
    return out


def _extract_reply_id(message: Any) -> str | None:
    if not isinstance(message, list):
        return None
    for seg in message:
        if not isinstance(seg, dict):
            continue
        if seg.get("type") != "reply":
            continue
        data = seg.get("data") or {}
        mid = data.get("id")
        if mid is not None:
            return str(mid)
    return None


def _api_ok(res: dict[str, Any]) -> bool:
    st = res.get("status")
    if st == "failed":
        return False
    rc = res.get("retcode")
    if rc is None:
        return True
    try:
        return int(rc) == 0
    except (TypeError, ValueError):
        return False


def _api_err(res: dict[str, Any]) -> str:
    d = res.get("data")
    if isinstance(d, dict) and d.get("msg"):
        return str(d["msg"])
    if res.get("wording"):
        return str(res["wording"])
    return str(res)


def _tpl_fill(tpl: str, mapping: dict[str, Any]) -> str:
    out = tpl
    for k, v in mapping.items():
        out = out.replace("{" + k + "}", str(v))
    return out


async def _is_super(uid: int, cfg: dict[str, Any]) -> bool:
    admins = _pick(cfg, "超管QQ", [])
    if not isinstance(admins, list):
        return False
    try:
        return uid in [int(x) for x in admins]
    except (TypeError, ValueError):
        return False


async def _is_group_admin(
    bot: Any, group_id: int, user_id: int
) -> bool:
    try:
        res = await bot.call_api(
            "get_group_member_info",
            {"group_id": group_id, "user_id": user_id, "no_cache": False},
        )
    except Exception:
        log.exception("get_group_member_info")
        return False
    if not _api_ok(res):
        return False
    data = res.get("data")
    if not isinstance(data, dict):
        return False
    role = str(data.get("role", "")).lower()
    return role in ("owner", "admin")


async def _can_admin(
    bot: Any, group_id: int, user_id: int, cfg: dict[str, Any]
) -> bool:
    if await _is_super(user_id, cfg):
        return True
    return await _is_group_admin(bot, group_id, user_id)


async def _send_group(bot: Any, group_id: int, text: str) -> None:
    await bot.call_api(
        "send_group_msg",
        {"group_id": group_id, "message": text},
    )


def _split_args(text: str) -> list[str]:
    return [x for x in text.strip().split() if x]


def _ent_body(plain: str, cfg: dict[str, Any]) -> str:
    """去掉命令前缀后的正文，供娱乐「精确」匹配（例如 #抽签 → 抽签）。"""
    p = str(_pick(cfg, "命令前缀", "#"))
    s = plain.strip()
    if s.startswith(p):
        return s[len(p) :].strip()
    return s


async def _handle_entertainment(
    plain: str,
    cfg: dict[str, Any],
    event: dict[str, Any],
    bot: Any,
) -> bool:
    items = _pick(cfg, "娱乐命令", [])
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict):
            continue
        words = _norm_words(item.get("词"))
        if not words:
            continue
        mode = str(item.get("匹配", "模糊"))
        is_exact = mode in ("精确", "exact")
        hit_word: str | None = None
        body = _ent_body(plain, cfg)
        for w in words:
            if is_exact:
                if body == w or plain.strip() == w:
                    hit_word = w
                    break
            elif w and w in plain:
                hit_word = w
                break
        if not hit_word:
            continue
        tpl = str(item.get("回复", "OK"))
        签文库 = _pick(cfg, "签文库", ["吉", "凶"])
        if not isinstance(签文库, list) or not 签文库:
            签文库 = ["吉"]
        tpl = tpl.replace("{签文}", str(random.choice(签文库)))
        tpl = tpl.replace("{点数}", str(random.randint(1, 6)))
        tpl = tpl.replace("{人品}", str(random.randint(0, 100)))
        tpl = tpl.replace("{random}", str(random.randint(1, 100)))
        if event.get("message_type") == "group":
            await _send_group(bot, int(event.get("group_id")), tpl)
        elif event.get("message_type") == "private":
            await bot.call_api(
                "send_private_msg",
                {"user_id": event.get("user_id"), "message": tpl},
            )
        log.info("group_suite 娱乐: %s", hit_word)
        return True
    return False


def _build_menu(cfg: dict[str, Any]) -> str:
    title = str(_pick(cfg, "菜单标题", "群管菜单"))
    prefix = str(_pick(cfg, "命令前缀", "#"))
    lines = [
        title,
        f"{prefix}菜单 — 显示本帮助",
        f"{prefix}禁言 @或QQ 秒数 — 禁言（需管理员）",
        f"{prefix}解除禁言 @或QQ — 解除禁言",
        f"{prefix}踢出 @成员 — 移出群聊",
        f"{prefix}全员禁言 / {prefix}解除全员禁言",
        f"{prefix}撤回 — 回复一条消息时撤回该条（需权限）",
        "娱乐：" + "、".join(
            w
            for ent in (_pick(cfg, "娱乐命令", []) or [])
            if isinstance(ent, dict)
            for w in _norm_words(ent.get("词"))[:2]
        ),
    ]
    return "\n".join(lines)


async def on_message(event: dict[str, Any], bot: Any) -> None:
    if not bot.connected:
        return
    msg = event.get("message")
    plain = extract_plain_text(msg).strip()
    if not plain:
        return

    cfg = _load_cfg()
    prefix = str(_pick(cfg, "命令前缀", "#"))
    if not plain.startswith(prefix):
        await _handle_entertainment(plain, cfg, event, bot)
        return

    body = plain[len(prefix) :].strip()
    if not body:
        return

    uid = event.get("user_id")
    if uid is None:
        return
    try:
        uid_i = int(uid)
    except (TypeError, ValueError):
        return

    parts = _split_args(body)
    head = parts[0] if parts else ""

    menu_words = _norm_words(_pick(cfg, "菜单命令词", ["菜单"]))
    if head in menu_words:
        text = _build_menu(cfg)
        if event.get("message_type") == "group":
            await _send_group(bot, int(event.get("group_id")), text)
        else:
            await bot.call_api("send_private_msg", {"user_id": uid_i, "message": text})
        return

    if event.get("message_type") != "group":
        tip = str(_pick(cfg, "仅群内回复", "此功能仅群内可用。"))
        await bot.call_api("send_private_msg", {"user_id": uid_i, "message": tip})
        return

    gid = int(event.get("group_id"))
    message = event.get("message")

    async def deny() -> None:
        await _send_group(
            bot,
            gid,
            str(_pick(cfg, "无权限回复", "你没有权限使用此命令。")),
        )

    async def fail(msg: str) -> None:
        pre = str(_pick(cfg, "操作失败前缀", ""))
        await _send_group(bot, gid, pre + msg)

    if not await _can_admin(bot, gid, uid_i, cfg):
        admin_words = (
            _norm_words(_pick(cfg, "禁言命令词", []))
            + _norm_words(_pick(cfg, "解除禁言命令词", []))
            + _norm_words(_pick(cfg, "踢人命令词", []))
            + _norm_words(_pick(cfg, "全员禁言开", []))
            + _norm_words(_pick(cfg, "全员禁言关", []))
            + _norm_words(_pick(cfg, "撤回命令词", []))
        )
        for w in admin_words:
            if head == w:
                await deny()
                return

    ats = _extract_at_qq(message)

    for w in _norm_words(_pick(cfg, "禁言命令词", [])):
        if head != w:
            continue
        if not await _can_admin(bot, gid, uid_i, cfg):
            await deny()
            return
        target = ats[0] if ats else None
        sec = None
        if len(parts) >= 2 and parts[-1].isdigit():
            sec = int(parts[-1])
            if target is None and len(parts) >= 3:
                try:
                    target = int(parts[1])
                except ValueError:
                    pass
        elif len(parts) >= 3 and parts[1].isdigit():
            try:
                target = int(parts[1])
            except ValueError:
                pass
            sec = int(parts[2]) if parts[2].isdigit() else None
        if target is None or sec is None:
            await _send_group(
                bot,
                gid,
                str(_pick(cfg, "参数错误禁言", "用法：#禁言 @成员 秒数")),
            )
            return
        res = await bot.call_api(
            "set_group_ban",
            {"group_id": gid, "user_id": target, "duration": sec},
        )
        if _api_ok(res):
            ok_tpl = str(
                _pick(cfg, "禁言成功模板", "已对 {target} 禁言 {sec} 秒。")
            )
            await _send_group(
                bot, gid, _tpl_fill(ok_tpl, {"target": target, "sec": sec})
            )
        else:
            await fail(_api_err(res))
        return

    for w in _norm_words(_pick(cfg, "解除禁言命令词", [])):
        if head != w:
            continue
        if not await _can_admin(bot, gid, uid_i, cfg):
            await deny()
            return
        target = ats[0] if ats else None
        if target is None and len(parts) >= 2:
            try:
                target = int(parts[1])
            except ValueError:
                pass
        if target is None:
            await _send_group(bot, gid, "用法：#解除禁言 @成员 或 QQ号")
            return
        res = await bot.call_api(
            "set_group_ban",
            {"group_id": gid, "user_id": target, "duration": 0},
        )
        if _api_ok(res):
            ok_tpl = str(
                _pick(cfg, "解除禁言成功模板", "已解除 {target} 的禁言。")
            )
            await _send_group(
                bot, gid, _tpl_fill(ok_tpl, {"target": target})
            )
        else:
            await fail(_api_err(res))
        return

    for w in _norm_words(_pick(cfg, "踢人命令词", [])):
        if head != w:
            continue
        if not await _can_admin(bot, gid, uid_i, cfg):
            await deny()
            return
        target = ats[0] if ats else None
        if target is None and len(parts) >= 2:
            try:
                target = int(parts[1])
            except ValueError:
                pass
        if target is None:
            await _send_group(
                bot,
                gid,
                str(_pick(cfg, "参数错误踢", "用法：#踢出 @成员")),
            )
            return
        reject = bool(_pick(cfg, "踢人拒绝再次加群", False))
        res = await bot.call_api(
            "set_group_kick",
            {
                "group_id": gid,
                "user_id": target,
                "reject_add_request": reject,
            },
        )
        if _api_ok(res):
            ok_tpl = str(_pick(cfg, "踢人成功模板", "已移出 {target}。"))
            await _send_group(
                bot, gid, _tpl_fill(ok_tpl, {"target": target})
            )
        else:
            await fail(_api_err(res))
        return

    for w in _norm_words(_pick(cfg, "全员禁言开", [])):
        if head != w:
            continue
        if not await _can_admin(bot, gid, uid_i, cfg):
            await deny()
            return
        res = await bot.call_api(
            "set_group_whole_ban",
            {"group_id": gid, "enable": True},
        )
        if _api_ok(res):
            ok_tpl = str(
                _pick(cfg, "全员禁言开成功", "已开启全员禁言。")
            )
            await _send_group(bot, gid, ok_tpl)
        else:
            await fail(_api_err(res))
        return

    for w in _norm_words(_pick(cfg, "全员禁言关", [])):
        if head != w:
            continue
        if not await _can_admin(bot, gid, uid_i, cfg):
            await deny()
            return
        res = await bot.call_api(
            "set_group_whole_ban",
            {"group_id": gid, "enable": False},
        )
        if _api_ok(res):
            ok_tpl = str(
                _pick(cfg, "全员禁言关成功", "已关闭全员禁言。")
            )
            await _send_group(bot, gid, ok_tpl)
        else:
            await fail(_api_err(res))
        return

    for w in _norm_words(_pick(cfg, "撤回命令词", [])):
        if head != w:
            continue
        if not await _can_admin(bot, gid, uid_i, cfg):
            await deny()
            return
        mid = _extract_reply_id(message)
        if not mid:
            await _send_group(bot, gid, "请回复要撤回的那条消息再发 #撤回")
            return
        try:
            mid_i = int(mid)
        except ValueError:
            await _send_group(bot, gid, "无法解析要撤回的消息 ID。")
            return
        res = await bot.call_api("delete_msg", {"message_id": mid_i})
        if _api_ok(res):
            cmd_mid = event.get("message_id")
            if cmd_mid is not None:
                try:
                    await bot.call_api(
                        "delete_msg", {"message_id": int(cmd_mid)}
                    )
                except Exception:
                    pass
            ok_tpl = str(_pick(cfg, "撤回成功模板", "已撤回目标消息。"))
            await _send_group(bot, gid, ok_tpl)
        else:
            await fail(_api_err(res))
        return

    rest = plain
    await _handle_entertainment(rest, cfg, event, bot)


async def on_notice(event: dict[str, Any], bot: Any) -> None:
    if not getattr(bot, "connected", False):
        return
    if event.get("notice_type") != "group_increase":
        return
    cfg = _load_cfg()
    if not bool(_pick(cfg, "进群发欢迎", False)):
        return
    gid = event.get("group_id")
    uid = event.get("user_id")
    if gid is None or uid is None:
        return
    try:
        gid_i = int(gid)
        uid_i = int(uid)
    except (TypeError, ValueError):
        return
    zc = getattr(bot, "config", None)
    if zc is not None:
        try:
            if gid_i not in set(zc.enabled_group_ids):
                return
        except Exception:
            pass
    tpl = str(_pick(cfg, "进群欢迎模板", "欢迎 {at} 进群！"))
    at_cq = f"[CQ:at,qq={uid_i}]"
    nick = str(uid_i)
    try:
        res = await bot.call_api(
            "get_group_member_info",
            {"group_id": gid_i, "user_id": uid_i, "no_cache": False},
        )
        if _api_ok(res) and isinstance(res.get("data"), dict):
            d = res["data"]
            card = d.get("card") or d.get("nickname")
            if card:
                nick = str(card)
    except Exception:
        log.exception("进群欢迎取名片")
    text = _tpl_fill(
        tpl,
        {
            "at": at_cq,
            "qq": uid_i,
            "nick": nick,
            "group": gid_i,
        },
    )
    try:
        await bot.call_api(
            "send_group_msg",
            {"group_id": gid_i, "message": text},
        )
    except Exception:
        log.exception("进群欢迎发送失败")
