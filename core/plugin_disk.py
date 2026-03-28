from __future__ import annotations

import re
from pathlib import Path

SYMBOL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
ENTRY_FILENAME = "plugin.py"
CONFIG_FILENAME = "config.json"
ADMIN_DIR = "admin"
DATA_DIR = "data"


def is_valid_symbol(name: str) -> bool:
    return bool(SYMBOL_PATTERN.fullmatch(name))


def admin_html_path(plugin_root: Path) -> Path | None:
    adm = plugin_root / ADMIN_DIR
    if not adm.is_dir():
        return None
    preferred = adm / "index.html"
    if preferred.is_file():
        return preferred
    htmls = sorted(adm.glob("*.html"))
    return htmls[0] if htmls else None


def iter_plugin_dirs(plugins_root: Path) -> list[Path]:
    if not plugins_root.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(plugins_root.iterdir()):
        if p.is_dir() and not p.name.startswith("_"):
            out.append(p)
    return out
