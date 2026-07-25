from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.notification_manager import NtfySettings
from core.paths import APP_SETTINGS_PATH, PROJECT_ROOT, ensure_runtime_directories


def default_server_root() -> Path:
    return PROJECT_ROOT / "servers"


def default_backup_root() -> Path:
    return PROJECT_ROOT / "backups"


@dataclass(frozen=True)
class AppSettings:
    server_root: Path
    backup_root: Path
    task_autostart: bool = False
    autostart_active_server: bool = False
    task_daily_maintenance: bool = False
    task_daily_time: str = "04:00"
    ntfy_enabled: bool = False
    ntfy_server_url: str = "https://ntfy.sh"
    ntfy_topic: str = ""

    def ntfy_settings(self) -> NtfySettings:
        return NtfySettings(
            enabled=self.ntfy_enabled,
            server_url=self.ntfy_server_url,
            topic=self.ntfy_topic,
        )


class SettingsManager:
    def __init__(self, settings_path: Path | None = None) -> None:
        ensure_runtime_directories()
        self.settings_path = settings_path or APP_SETTINGS_PATH
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> AppSettings:
        defaults = self.defaults()
        if not self.settings_path.exists():
            self.save(defaults)
            return defaults
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return defaults
        server_value = str(data.get("server_root", "")).strip()
        backup_value = str(data.get("backup_root", "")).strip()
        return AppSettings(
            server_root=Path(server_value).expanduser() if server_value else defaults.server_root,
            backup_root=Path(backup_value).expanduser() if backup_value else defaults.backup_root,
            task_autostart=bool(data.get("task_autostart", False)),
            autostart_active_server=bool(data.get("autostart_active_server", data.get("task_autostart", False))),
            task_daily_maintenance=bool(data.get("task_daily_maintenance", False)),
            task_daily_time=str(data.get("task_daily_time", "04:00")),
            ntfy_enabled=bool(data.get("ntfy_enabled", False)),
            ntfy_server_url=str(data.get("ntfy_server_url", "https://ntfy.sh")),
            ntfy_topic=str(data.get("ntfy_topic", "")),
        )

    def save(self, settings: AppSettings) -> None:
        server_root = settings.server_root.expanduser().resolve()
        backup_root = settings.backup_root.expanduser().resolve()
        server_root.mkdir(parents=True, exist_ok=True)
        backup_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 3,
            "server_root": str(server_root),
            "backup_root": str(backup_root),
            "task_autostart": settings.task_autostart,
            "autostart_active_server": settings.autostart_active_server,
            "task_daily_maintenance": settings.task_daily_maintenance,
            "task_daily_time": settings.task_daily_time,
            "ntfy_enabled": settings.ntfy_enabled,
            "ntfy_server_url": settings.ntfy_server_url,
            "ntfy_topic": settings.ntfy_topic,
        }
        temp_path = self.settings_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.settings_path)

    @staticmethod
    def defaults() -> AppSettings:
        return AppSettings(server_root=default_server_root(), backup_root=default_backup_root())
