"""从 plugin.py 静态解析 display_name / plugin_author（不执行代码），供列表展示。"""

from __future__ import annotations

import ast
from pathlib import Path


def parse_plugin_py_metadata(plugin_py: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not plugin_py.is_file():
        return out
    try:
        src = plugin_py.read_text(encoding="utf-8")
    except OSError:
        return out
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out

    def str_from(node: ast.AST | None) -> str | None:
        if node is None:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if not isinstance(t, ast.Name):
                continue
            val = str_from(node.value)
            if val is None:
                continue
            if t.id == "display_name":
                out["display_name"] = val
            elif t.id == "plugin_author":
                out["plugin_author"] = val
            elif t.id == "__author__" and "plugin_author" not in out:
                out["plugin_author"] = val
    return out
