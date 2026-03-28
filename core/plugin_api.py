from __future__ import annotations

from typing import Any, Protocol


class BotAPI(Protocol):
    async def call_api(self, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    @property
    def connected(self) -> bool: ...


class ZexPlugin(Protocol):
    """插件约定：display_name；可选 plugin_author 或模块级 __author__；以及各事件钩子。"""

    pass
