"""ZexBot 入口：启动 Web 控制台与机器人宿主。"""

from __future__ import annotations

import socket
import sys
import threading
import webbrowser
from pathlib import Path

# 允许在 zexbot 目录内直接执行 py main.py：须先把「包含 zexbot 包的那一層」加入 path
_PKG_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _PKG_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import uvicorn

from zexbot.core.config import load_config
from zexbot.core.runtime_paths import bootstrap_plugins_if_frozen, user_data_dir


def _find_listen_port(host: str, preferred: int, max_attempts: int = 40) -> tuple[int, bool]:
    """
    检测本地能否绑定端口；若 preferred 被占用则依次 +1 尝试。
    返回 (实际端口, 是否偏离了配置端口)。
    """
    h = host.strip()
    if h in ("::", "[::]"):
        family = socket.AF_INET6
        bind = "::"
    else:
        family = socket.AF_INET
        bind = "0.0.0.0" if h in ("0.0.0.0", "") else h

    for i in range(max_attempts):
        port = preferred + i
        if port > 65535:
            break
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((bind, port))
        except OSError:
            continue
        return port, i > 0

    raise RuntimeError(
        f"端口 {preferred}～{min(preferred + max_attempts - 1, 65535)} 均被占用。"
        "请关闭占用进程，或编辑 data/config.json（exe 同目录下）修改 web_port。"
    )


def _browser_url(host: str, port: int) -> str:
    h = host.strip()
    if h in ("0.0.0.0", "::", ""):
        h = "127.0.0.1"
    return f"http://{h}:{port}/"


def main() -> None:
    # 打包后字符串路径 import 在部分环境下会失败，改用手握 app 对象
    if getattr(sys, "frozen", False):
        meip = getattr(sys, "_MEIPASS", None)
        if meip and str(meip) not in sys.path:
            sys.path.insert(0, str(meip))

    bootstrap_plugins_if_frozen()
    cfg = load_config(user_data_dir())

    port, port_fallback = _find_listen_port(cfg.web_host, cfg.web_port)
    if port_fallback:
        print(
            f"[ZexBot] 配置的 web_port={cfg.web_port} 已被占用，本次启动改用 {port}。\n"
            f"         本机地址: {_browser_url(cfg.web_host, port)}\n"
            "         若需固定端口，请结束占用原端口的程序，或修改 exe 同目录 data/config.json。",
            flush=True,
        )

    def open_browser() -> None:
        try:
            webbrowser.open(_browser_url(cfg.web_host, port))
        except OSError:
            pass

    threading.Timer(0.75, open_browser).start()

    if getattr(sys, "frozen", False):
        from zexbot.app import app as fastapi_app

        uvicorn.run(
            fastapi_app,
            host=cfg.web_host,
            port=port,
            reload=False,
        )
    else:
        uvicorn.run(
            "zexbot.app:app",
            host=cfg.web_host,
            port=port,
            reload=False,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        if getattr(sys, "frozen", False):
            input("ZexBot 启动失败，请查看上方错误信息。按回车键退出…")
        raise
