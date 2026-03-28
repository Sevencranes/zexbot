from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from zexbot.core.config import ZexConfig
from zexbot.core.plugin_disk import ENTRY_FILENAME, admin_html_path, is_valid_symbol, iter_plugin_dirs

log = logging.getLogger("zexbot.plugins")


def _module_author(module: ModuleType) -> str:
    for key in ("plugin_author", "__author__"):
        v = getattr(module, key, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


class PluginContext:
    def __init__(self, symbol: str, root: Path, module: ModuleType) -> None:
        self.symbol = symbol
        self.root = root.resolve()
        self.module = module
        self.name = getattr(module, "display_name", None) or symbol
        if not isinstance(self.name, str):
            self.name = symbol
        self.author = _module_author(module)


class PluginsHost:
    def __init__(self) -> None:
        self._loaded: list[PluginContext] = []
        self._by_symbol: dict[str, PluginContext] = {}
        self._load_errors: dict[str, str] = {}

    def load_directory(self, directory: Path) -> None:
        self.unload_all()
        if not directory.is_dir():
            directory.mkdir(parents=True, exist_ok=True)
            return
        for sub in iter_plugin_dirs(directory):
            sym = sub.name
            if not is_valid_symbol(sym):
                log.warning("跳过非法插件目录名: %s（须英文字母开头，仅字母数字下划线）", sym)
                continue
            main = sub / ENTRY_FILENAME
            if not main.is_file():
                log.warning("跳过插件 %s：缺少 %s", sym, ENTRY_FILENAME)
                continue
            try:
                ctx = self._load_package(sym, sub, main)
                self._loaded.append(ctx)
                self._by_symbol[sym] = ctx
                log.info("插件已加载: %s (%s)", ctx.name, sym)
            except Exception as e:
                self._load_errors[sym] = f"{type(e).__name__}: {e}"
                log.exception("加载插件失败 %s", sub)

    @property
    def load_errors(self) -> dict[str, str]:
        return dict(self._load_errors)

    def _load_package(self, symbol: str, root: Path, main: Path) -> PluginContext:
        mod_name = f"zexbot_pkg_{symbol}"
        spec = importlib.util.spec_from_file_location(mod_name, main)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法加载 {main}")
        mod = importlib.util.module_from_spec(spec)
        mod.__zexbot_plugin_root__ = str(root)
        mod.__zexbot_plugin_symbol__ = symbol
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return PluginContext(symbol, root, mod)

    def unload_all(self) -> None:
        for ctx in self._loaded:
            sys.modules.pop(f"zexbot_pkg_{ctx.symbol}", None)
        self._loaded.clear()
        self._by_symbol.clear()
        self._load_errors.clear()

    def context(self, symbol: str) -> PluginContext | None:
        return self._by_symbol.get(symbol)

    async def run_hooks(
        self,
        hook: str,
        *args: Any,
        cfg: ZexConfig | None = None,
    ) -> None:
        disabled = set(cfg.disabled_plugins) if cfg is not None else set()
        for ctx in self._loaded:
            if ctx.symbol in disabled:
                continue
            fn = getattr(ctx.module, hook, None)
            if callable(fn):
                try:
                    res = fn(*args)
                    if hasattr(res, "__await__"):
                        await res  # type: ignore[misc]
                except Exception:
                    log.exception("插件 %s 钩子 %s 异常", ctx.symbol, hook)

    @property
    def plugins(self) -> list[dict[str, str]]:
        return [
            {
                "symbol": c.symbol,
                "name": c.name,
                "module": c.module.__name__,
                "author": c.author,
            }
            for c in self._loaded
        ]
