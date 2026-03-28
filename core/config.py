from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "config.json"


def _migrate_legacy_config() -> None:
    """若旧版把配置放在项目根目录的 data/，首次启动时复制到 zexbot/data/。打包 exe 不迁移。"""
    from zexbot.core.runtime_paths import bundle_root, is_frozen, user_data_dir

    if is_frozen():
        return
    new_file = user_data_dir() / CONFIG_FILENAME
    old_file = bundle_root().parent / "data" / CONFIG_FILENAME
    if new_file.is_file() or not old_file.is_file():
        return
    new_file.parent.mkdir(parents=True, exist_ok=True)
    new_file.write_bytes(old_file.read_bytes())


@dataclass
class ZexConfig:
    ws_url: str = "ws://127.0.0.1:3001"
    token: str = ""
    private_message_enabled: bool = True
    enabled_group_ids: list[int] = field(default_factory=list)
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    plugins_dir: str = "plugins"
    disabled_plugins: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ZexConfig:
        raw_dp = d.get("disabled_plugins", [])
        if not isinstance(raw_dp, list):
            raw_dp = []
        return cls(
            ws_url=str(d.get("ws_url", cls.ws_url)),
            token=str(d.get("token", "")),
            private_message_enabled=bool(d.get("private_message_enabled", True)),
            enabled_group_ids=[int(x) for x in d.get("enabled_group_ids", [])],
            web_host=str(d.get("web_host", "0.0.0.0")),
            web_port=int(d.get("web_port", 8080)),
            plugins_dir=str(d.get("plugins_dir", "plugins")),
            disabled_plugins=[str(x) for x in raw_dp],
        )


def config_path(base: Path | None = None) -> Path:
    from zexbot.core.runtime_paths import user_data_dir

    root = base or user_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root / CONFIG_FILENAME


def load_config(base: Path | None = None) -> ZexConfig:
    from zexbot.core.runtime_paths import user_data_dir

    root = base or user_data_dir()
    if root.resolve() == user_data_dir().resolve():
        _migrate_legacy_config()
    path = config_path(base)
    if not path.is_file():
        cfg = ZexConfig()
        save_config(cfg, base)
        return cfg
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return ZexConfig.from_dict(raw)


def save_config(cfg: ZexConfig, base: Path | None = None) -> None:
    path = config_path(base)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, ensure_ascii=False, indent=2)
