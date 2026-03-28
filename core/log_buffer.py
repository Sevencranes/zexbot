from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone


class RingLogHandler(logging.Handler):
    def __init__(self, maxlen: int = 1000) -> None:
        super().__init__()
        self._lines: deque[str] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._lines.append(msg)
        except Exception:
            self.handleError(record)

    def get_lines(self, last: int | None = None) -> list[str]:
        items = list(self._lines)
        if last is not None and last > 0:
            return items[-last:]
        return items

    def clear(self) -> None:
        self._lines.clear()


def utc_now_str() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
