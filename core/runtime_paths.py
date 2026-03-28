"""
运行路径：PyInstaller 打包后配置与插件放在 exe 同目录（与 LLBot 同风格），只读资源在 _MEIPASS。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

__all__ = [
    "is_frozen",
    "bundle_root",
    "exe_dir",
    "user_data_dir",
    "plugins_disk_root",
    "bootstrap_plugins_if_frozen",
]


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def exe_dir() -> Path | None:
    if not is_frozen():
        return None
    return Path(sys.executable).resolve().parent


def bundle_root() -> Path:
    """内置资源根（web、默认插件模板）：开发时为 zexbot 包目录；frozen 为 _MEIPASS/zexbot。"""
    if is_frozen():
        base = getattr(sys, "_MEIPASS", None)
        if not base:
            raise RuntimeError("frozen 但未设置 _MEIPASS")
        return Path(base) / "zexbot"
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    """可写配置目录：frozen 时为 exe 同目录 data/。"""
    if is_frozen():
        d = exe_dir() / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d
    root = bundle_root() / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def plugins_disk_root(plugins_subdir: str) -> Path:
    """插件所在磁盘目录（可写）。frozen 时为 exe 同目录下子目录。"""
    name = (plugins_subdir or "plugins").strip() or "plugins"
    if is_frozen():
        ed = exe_dir()
        if ed is None:
            raise RuntimeError("exe_dir 不可用")
        p = ed / name
        p.mkdir(parents=True, exist_ok=True)
        return p.resolve()
    return (bundle_root() / name).resolve()


def bootstrap_plugins_if_frozen() -> None:
    """首次运行：把内置 plugins 复制到 exe 同目录，便于插件读写 data、用户可替换。"""
    if not is_frozen():
        return
    ed = exe_dir()
    if ed is None:
        return
    dst = ed / "plugins"
    if dst.is_dir() and any(dst.iterdir()):
        return
    src = bundle_root() / "plugins"
    if not src.is_dir():
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
