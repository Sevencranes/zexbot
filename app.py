from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from zexbot import __author__, __version__
from zexbot.core.bot_runner import BotRunner, OneBotClient
from zexbot.core.config import ZexConfig, load_config, save_config
from zexbot.core.log_buffer import RingLogHandler
from zexbot.core.plugin_disk import admin_html_path, is_valid_symbol, iter_plugin_dirs
from zexbot.core.plugin_meta import parse_plugin_py_metadata
from zexbot.core.plugins_host import PluginsHost
from zexbot.core.runtime_paths import (
    bootstrap_plugins_if_frozen,
    bundle_root,
    plugins_disk_root,
    user_data_dir,
)

bootstrap_plugins_if_frozen()

PACKAGE_ROOT = bundle_root()
STATIC = PACKAGE_ROOT / "web" / "static"
DATA_DIR = user_data_dir()

ring_handler = RingLogHandler(1200)
plugins_host = PluginsHost()

_config: ZexConfig = load_config(DATA_DIR)
_groups_cache: list[dict[str, Any]] = []


async def _refresh_groups_cache_impl(ob_client: OneBotClient | None = None) -> int:
    """调用 get_group_list 并写入内存缓存。可传入刚连上的 client，避免与 runner.client() 瞬时不一致。"""
    global _groups_cache
    c = ob_client if ob_client is not None else runner.client()
    if c is None or not c.connected:
        raise RuntimeError("机器人未连接，无法刷新群列表")
    res = await c.call_api("get_group_list", {})
    if res.get("status") == "failed":
        raise RuntimeError(str(res))
    rc = res.get("retcode")
    if rc is not None and int(rc) != 0:
        raise RuntimeError(str(res))
    data = res.get("data")
    if not isinstance(data, list):
        _groups_cache = []
    else:
        _groups_cache = data
    return len(_groups_cache)


async def _on_bot_connected(client: OneBotClient) -> None:
    try:
        n = await _refresh_groups_cache_impl(client)
        log.info("连接成功后已自动刷新群列表: %s 个", n)
    except Exception as e:
        log.warning("连接成功后自动刷新群列表失败: %s", e)


runner = BotRunner(plugins_host, on_connected=_on_bot_connected)


def setup_logging() -> None:
    """将环形缓冲挂到 root；应用启动时再执行一次，避免 uvicorn 重置 logging 后插件日志丢失。"""
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root = logging.getLogger()
    ring_handler.setFormatter(fmt)
    if not any(isinstance(h, RingLogHandler) for h in root.handlers):
        root.addHandler(ring_handler)
    root.setLevel(logging.INFO)
    for name in ("zexbot", "uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.INFO)
        logging.getLogger(name).propagate = True


setup_logging()
log = logging.getLogger("zexbot.web")


def _plugins_root() -> Path:
    return plugins_disk_root(_config.plugins_dir)


def reload_plugins() -> None:
    plugins_host.load_directory(plugins_disk_root(_config.plugins_dir))


reload_plugins()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield
    await runner.stop()


app = FastAPI(title="ZexBot", version=__version__, lifespan=lifespan)


@app.get("/api/meta")
def meta():
    return {"name": "ZexBot", "version": __version__, "author": __author__}


class ConfigBody(BaseModel):
    ws_url: str | None = None
    token: str | None = None
    private_message_enabled: bool | None = None
    enabled_group_ids: list[int] | None = None
    web_host: str | None = None
    web_port: int | None = None
    plugins_dir: str | None = None


@app.get("/api/config")
def get_config():
    global _config
    return _config.to_dict()


@app.put("/api/config")
async def put_config(body: ConfigBody):
    global _config
    d = _config.to_dict()
    if body.ws_url is not None:
        d["ws_url"] = body.ws_url
    if body.token is not None:
        d["token"] = body.token
    if body.private_message_enabled is not None:
        d["private_message_enabled"] = body.private_message_enabled
    if body.enabled_group_ids is not None:
        d["enabled_group_ids"] = body.enabled_group_ids
    if body.web_host is not None:
        d["web_host"] = body.web_host
    if body.web_port is not None:
        d["web_port"] = body.web_port
    if body.plugins_dir is not None:
        d["plugins_dir"] = body.plugins_dir
    _config = ZexConfig.from_dict(d)
    await runner.update_config(_config)
    if body.plugins_dir is not None:
        reload_plugins()
    return {"ok": True, "config": _config.to_dict()}


@app.post("/api/config/save")
def save_config_disk():
    save_config(_config, DATA_DIR)
    log.info("配置已写入磁盘")
    return {"ok": True}


@app.post("/api/config/reload")
async def reload_config_disk():
    global _config
    _config = load_config(DATA_DIR)
    reload_plugins()
    await runner.update_config(_config)
    log.info("配置已从磁盘重载")
    return {"ok": True, "config": _config.to_dict()}


@app.get("/api/status")
def status():
    c = runner.client()
    return {
        "running": runner.running,
        "connected": runner.connected,
        "plugins": plugins_host.plugins,
        "disabled_plugins": _config.disabled_plugins,
    }


def _plugins_list_payload() -> dict[str, Any]:
    root = _plugins_root()
    disabled = set(_config.disabled_plugins)
    titles = {p["symbol"]: p["name"] for p in plugins_host.plugins}
    authors = {p["symbol"]: p.get("author") or "" for p in plugins_host.plugins}
    load_errs = plugins_host.load_errors
    items: list[dict[str, Any]] = []
    for sub in iter_plugin_dirs(root):
        sym = sub.name
        vs = is_valid_symbol(sym)
        py = sub / "plugin.py"
        hm = py.is_file()
        valid = vs and hm
        err: str | None = None
        if not vs:
            err = "目录名须为英文字母开头，仅含字母、数字、下划线"
        elif not hm:
            err = "缺少 plugin.py"
        meta = parse_plugin_py_metadata(py) if hm else {}
        title = titles.get(sym) or meta.get("display_name") or sym
        author = authors.get(sym) or meta.get("plugin_author") or ""
        adm = admin_html_path(sub)
        loaded = sym in titles
        load_error = load_errs.get(sym) if not loaded and hm else None
        items.append(
            {
                "symbol": sym,
                "title": title,
                "author": author,
                "valid": valid,
                "error": err,
                "load_error": load_error,
                "enabled": sym not in disabled,
                "has_admin": adm is not None,
                "loaded": loaded,
            }
        )
    items.sort(key=lambda x: x["symbol"])
    return {"plugins": items}


@app.get("/api/plugins")
def plugins_list():
    """插件列表（请优先使用本路径；部分浏览器扩展会拦截 URL 中含 catalog 的请求）。"""
    return _plugins_list_payload()


@app.get("/api/plugins/catalog")
def plugins_catalog():
    return _plugins_list_payload()


class PluginEnabledBody(BaseModel):
    enabled: bool


@app.put("/api/plugins/{symbol}/enabled")
async def plugin_set_enabled(symbol: str, body: PluginEnabledBody):
    global _config
    if not is_valid_symbol(symbol):
        raise HTTPException(404, "无效的插件标识")
    plug = _plugins_root() / symbol
    if not plug.is_dir():
        raise HTTPException(404, "插件目录不存在")
    s = set(_config.disabled_plugins)
    if body.enabled:
        s.discard(symbol)
    else:
        s.add(symbol)
    _config.disabled_plugins = sorted(s)
    await runner.update_config(_config)
    save_config(_config, DATA_DIR)
    return {"ok": True, "disabled_plugins": _config.disabled_plugins}


@app.get("/api/plugins/{symbol}/config")
def get_plugin_config(symbol: str):
    if not is_valid_symbol(symbol):
        raise HTTPException(404, "无效的插件标识")
    plug = _plugins_root() / symbol
    if not plug.is_dir():
        raise HTTPException(404, "插件目录不存在")
    path = plug / "config.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"配置文件不是合法 JSON: {e}") from e


@app.put("/api/plugins/{symbol}/config")
async def put_plugin_config(symbol: str, body: dict[str, Any] = Body(...)):
    if not is_valid_symbol(symbol):
        raise HTTPException(404, "无效的插件标识")
    plug = _plugins_root() / symbol
    if not plug.is_dir():
        raise HTTPException(404, "插件目录不存在")
    path = plug / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    ctx = plugins_host.context(symbol)
    if ctx:
        fn = getattr(ctx.module, "on_config_updated", None)
        if callable(fn):
            res = fn()
            if hasattr(res, "__await__"):
                await res  # type: ignore[misc]
    log.info("插件 %s 配置已更新", symbol)
    return {"ok": True}


@app.get("/api/plugins/{symbol}/admin")
def get_plugin_admin(symbol: str):
    if not is_valid_symbol(symbol):
        raise HTTPException(404, "无效的插件标识")
    plug = _plugins_root() / symbol
    p = admin_html_path(plug)
    if p is None or not p.is_file():
        raise HTTPException(404, "该插件未提供 admin 配置页")
    try:
        resolved = p.resolve()
        plug_real = plug.resolve()
        if not str(resolved).startswith(str(plug_real)):
            raise HTTPException(403, "路径无效")
    except OSError:
        raise HTTPException(403, "路径无效") from None
    return FileResponse(resolved, media_type="text/html; charset=utf-8")


@app.post("/api/bot/start")
async def bot_start():
    global _config
    if runner.running:
        raise HTTPException(400, "机器人已在运行")
    _config = load_config(DATA_DIR)
    reload_plugins()
    try:
        await runner.start(_config)
    except Exception as e:
        log.exception("启动失败")
        raise HTTPException(500, str(e)) from e
    return {"ok": True}


@app.post("/api/bot/stop")
async def bot_stop():
    await runner.stop()
    return {"ok": True}


@app.get("/api/logs")
def api_logs(limit: int = 500):
    return {"lines": ring_handler.get_lines(last=limit)}


@app.post("/api/logs/clear")
def api_logs_clear():
    ring_handler.clear()
    log.info("内存日志缓冲已清空")
    return {"ok": True}


class GroupToggleBody(BaseModel):
    group_id: int
    enabled: bool


@app.get("/api/groups")
def list_groups():
    enabled = set(_config.enabled_group_ids)
    enabled_list = []
    disabled_list = []
    for g in _groups_cache:
        gid = int(g.get("group_id", 0))
        name = str(g.get("group_name", g.get("name", str(gid))))
        item = {"group_id": gid, "group_name": name}
        if gid in enabled:
            enabled_list.append(item)
        else:
            disabled_list.append(item)
    enabled_list.sort(key=lambda x: x["group_id"])
    disabled_list.sort(key=lambda x: x["group_id"])
    return {
        "connected": runner.connected,
        "enabled": enabled_list,
        "disabled": disabled_list,
    }


@app.post("/api/groups/refresh")
async def refresh_groups():
    try:
        n = await _refresh_groups_cache_impl()
    except RuntimeError as e:
        msg = str(e)
        if "未连接" in msg:
            raise HTTPException(503, msg) from e
        raise HTTPException(500, f"API 错误: {msg}") from e
    except Exception as e:
        log.exception("get_group_list 失败")
        raise HTTPException(500, str(e)) from e
    log.info("群列表已刷新: %s 个", n)
    return {"ok": True, "count": n}


@app.post("/api/groups/toggle")
async def toggle_group(body: GroupToggleBody):
    global _config
    ids = list(_config.enabled_group_ids)
    s = set(ids)
    if body.enabled:
        s.add(int(body.group_id))
    else:
        s.discard(int(body.group_id))
    _config.enabled_group_ids = sorted(s)
    await runner.update_config(_config)
    save_config(_config, DATA_DIR)
    return {"ok": True, "enabled_group_ids": _config.enabled_group_ids}


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
def index():
    index_path = STATIC.parent / "index.html"
    return FileResponse(index_path)
