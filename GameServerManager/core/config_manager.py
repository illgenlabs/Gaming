from __future__ import annotations

import json
from pathlib import Path

from core.paths import SERVERS_CONFIG_PATH, ensure_runtime_directories
from models import ServerInfo


class ConfigManager:
    def __init__(self, config_path: Path | None = None) -> None:
        ensure_runtime_directories()
        self.config_path = config_path or SERVERS_CONFIG_PATH
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def load_servers(self) -> list[ServerInfo]:
        if not self.config_path.exists():
            self.save_servers([])
            return []
        try:
            with self.config_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return []
        return [ServerInfo.from_dict(item) for item in data.get("servers", []) if isinstance(item, dict)]

    def save_servers(self, servers: list[ServerInfo]) -> None:
        payload = {"version": 1, "servers": [server.to_dict() for server in servers]}
        temp_path = self.config_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        temp_path.replace(self.config_path)
