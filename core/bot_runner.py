from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from zexbot.core.config import ZexConfig
from zexbot.core.plugins_host import PluginsHost

log = logging.getLogger("zexbot.bot")


class OneBotClient:
    """OneBot 11 正向 WebSocket 客户端（与 LLBot / LLOneBot 等常见实现兼容）。"""

    def __init__(
        self,
        cfg: ZexConfig,
        plugins: PluginsHost,
        on_event: Any | None = None,
        on_connected: Callable[["OneBotClient"], Awaitable[None]] | None = None,
    ) -> None:
        self._cfg = cfg
        self._plugins = plugins
        self._ws: ClientConnection | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._recv_task: asyncio.Task[None] | None = None
        self._closed = asyncio.Event()
        self._on_event = on_event
        self._on_connected = on_connected

    @property
    def connected(self) -> bool:
        return self._ws is not None and self._ws.close_code is None

    async def connect(self) -> None:
        extra_headers: list[tuple[str, str]] = []
        if self._cfg.token.strip():
            extra_headers.append(("Authorization", f"Bearer {self._cfg.token.strip()}"))

        self._ws = await websockets.connect(
            self._cfg.ws_url.strip(),
            additional_headers=extra_headers,
            max_size=2**24,
            ping_interval=20,
            ping_timeout=20,
        )
        self._closed.clear()
        self._recv_task = asyncio.create_task(self._recv_loop())
        log.info("WebSocket 已连接: %s", self._cfg.ws_url)
        await self._plugins.run_hooks("on_connect", self, cfg=self._cfg)
        if self._on_connected:
            try:
                await self._on_connected(self)
            except Exception:
                log.exception("on_connected 回调异常")

    async def close(self) -> None:
        self._closed.set()
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
            self._recv_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        for f in self._pending.values():
            if not f.done():
                f.set_exception(RuntimeError("连接已关闭"))
        self._pending.clear()
        await self._plugins.run_hooks("on_disconnect", self, cfg=self._cfg)
        log.info("WebSocket 已断开")

    async def call_api(self, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("未连接")
        echo = str(uuid.uuid4())
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[echo] = fut
        payload = {"action": action, "params": params or {}, "echo": echo}
        await self._ws.send(json.dumps(payload, ensure_ascii=False))
        try:
            return await asyncio.wait_for(fut, timeout=60.0)
        finally:
            self._pending.pop(echo, None)

    @property
    def config(self) -> ZexConfig:
        return self._cfg

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    log.warning("非 JSON 消息: %s", raw[:200])
                    continue
                if "echo" in data and ("status" in data or "retcode" in data):
                    echo = str(data.get("echo", ""))
                    fut = self._pending.get(echo)
                    if fut and not fut.done():
                        fut.set_result(data)
                    continue
                # 不阻塞接收循环：并行处理事件，避免首条回复后后续消息堆积、迟迟不处理
                asyncio.create_task(self._safe_dispatch(data), name="zexbot-dispatch")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if not self._closed.is_set():
                log.exception("接收循环异常: %s", e)
        finally:
            self._closed.set()

    async def _safe_dispatch(self, data: dict[str, Any]) -> None:
        try:
            await self._dispatch_event(data)
        except Exception:
            log.exception("事件分发异常")

    async def _dispatch_event(self, data: dict[str, Any]) -> None:
        if self._on_event:
            try:
                await self._on_event(data)
            except Exception:
                log.exception("on_event 异常")

        post_type = data.get("post_type")
        if post_type == "message":
            if not await self._should_handle_message(data):
                return
            await self._plugins.run_hooks("on_message", data, self, cfg=self._cfg)
        elif post_type == "notice":
            await self._plugins.run_hooks("on_notice", data, self, cfg=self._cfg)
        elif post_type == "request":
            await self._plugins.run_hooks("on_request", data, self, cfg=self._cfg)
        else:
            await self._plugins.run_hooks("on_raw_event", data, self, cfg=self._cfg)

    async def _should_handle_message(self, data: dict[str, Any]) -> bool:
        mt = data.get("message_type")
        if mt == "private":
            return self._cfg.private_message_enabled
        if mt == "group":
            gid = data.get("group_id")
            if gid is None:
                return False
            try:
                gid_i = int(gid)
            except (TypeError, ValueError):
                return False
            return gid_i in set(self._cfg.enabled_group_ids)
        return True


class BotRunner:
    def __init__(
        self,
        plugins: PluginsHost,
        on_connected: Callable[[OneBotClient], Awaitable[None]] | None = None,
    ) -> None:
        self._plugins = plugins
        self._on_connected = on_connected
        self._client: OneBotClient | None = None
        self._task: asyncio.Task[None] | None = None
        self._cfg: ZexConfig | None = None
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.connected

    def client(self) -> OneBotClient | None:
        return self._client

    async def start(self, cfg: ZexConfig) -> None:
        async with self._lock:
            if self.running:
                raise RuntimeError("机器人已在运行")
            self._cfg = cfg
            self._client = OneBotClient(
                cfg, self._plugins, on_connected=self._on_connected
            )
            self._task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        async with self._lock:
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
                self._task = None
            if self._client:
                await self._client.close()
                self._client = None

    async def update_config(self, cfg: ZexConfig) -> None:
        self._cfg = cfg
        if self._client:
            self._client._cfg = cfg  # noqa: SLF001

    async def _run_forever(self) -> None:
        assert self._client is not None
        backoff = 1.0
        while self.running:
            try:
                await self._client.connect()
                backoff = 1.0
                await self._client._closed.wait()  # noqa: SLF001
            except asyncio.CancelledError:
                await self._client.close()
                raise
            except Exception as e:
                log.exception("连接失败: %s，%s 秒后重试", e, backoff)
                await self._client.close()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
                continue
            await self._client.close()
