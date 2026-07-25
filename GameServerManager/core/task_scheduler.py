from __future__ import annotations

import getpass
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


LEGACY_AUTOSTART_TASK_NAME = "Game Server Manager - Autostart"
LEGACY_MAINTENANCE_TASK_NAME = "Game Server Manager - Daily Maintenance"
STARTUP_FILE_NAME = "GameServerManager.cmd"


@dataclass(frozen=True)
class TaskState:
    autostart_enabled: bool
    maintenance_enabled: bool


class TaskSchedulerManager:
    """Manage per-user Windows startup and daily maintenance entries.

    Autostart uses the current user's Startup folder and therefore does not
    require administrator rights. Daily maintenance uses a per-user,
    interactive Task Scheduler entry.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        username = re.sub(r"[^A-Za-z0-9_.-]+", "_", getpass.getuser()) or "User"
        self.maintenance_task_name = (
            f"Game Server Manager - Daily Maintenance - {username}"
        )

    @property
    def supported(self) -> bool:
        return os.name == "nt"

    def command_parts(self, argument: str) -> list[str]:
        """Build a command from the location currently running the manager."""
        if getattr(sys, "frozen", False):
            return [str(Path(sys.executable).resolve()), argument]
        main_path = (self.project_root / "main.py").resolve()
        return [str(Path(sys.executable).resolve()), str(main_path), argument]

    def command_for(self, argument: str) -> str:
        return subprocess.list2cmdline(self.command_parts(argument))

    def configure_autostart(self, enabled: bool, start_active_server: bool = False) -> None:
        self._require_windows()
        startup_file = self._startup_file()
        if not enabled:
            startup_file.unlink(missing_ok=True)
            self._delete_legacy_task_best_effort(LEGACY_AUTOSTART_TASK_NAME)
            return

        startup_file.parent.mkdir(parents=True, exist_ok=True)
        command = self.command_for("--start-active" if start_active_server else "--show")
        content = "@echo off\r\nstart \"\" " + command + "\r\n"
        startup_file.write_text(content, encoding="utf-8")
        self._delete_legacy_task_best_effort(LEGACY_AUTOSTART_TASK_NAME)

    def configure_daily_maintenance(self, enabled: bool, time_value: str) -> None:
        self._require_windows()
        if not enabled:
            self._delete_task(self.maintenance_task_name)
            self._delete_legacy_task_best_effort(LEGACY_MAINTENANCE_TASK_NAME)
            return

        normalized = self.validate_time(time_value)
        current_user = self._current_windows_user()
        self._run_schtasks([
            "/Create", "/F",
            "/TN", self.maintenance_task_name,
            "/SC", "DAILY",
            "/ST", normalized,
            "/TR", self.command_for("--scheduled-maintenance"),
            "/RU", current_user,
            "/IT",
            "/RL", "LIMITED",
        ])
        self._delete_legacy_task_best_effort(LEGACY_MAINTENANCE_TASK_NAME)

    def state(self) -> TaskState:
        if not self.supported:
            return TaskState(False, False)
        return TaskState(
            autostart_enabled=self._startup_file().exists(),
            maintenance_enabled=self._task_exists(self.maintenance_task_name),
        )

    @staticmethod
    def validate_time(value: str) -> str:
        parts = value.strip().split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("The maintenance time must use the 24-hour format HH:MM.")
        hour, minute = (int(part) for part in parts)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("The maintenance time must be between 00:00 and 23:59.")
        return f"{hour:02d}:{minute:02d}"

    def _startup_file(self) -> Path:
        appdata = os.environ.get("APPDATA", "").strip()
        if not appdata:
            raise RuntimeError("The Windows APPDATA folder could not be determined.")
        return (
            Path(appdata)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
            / STARTUP_FILE_NAME
        )

    @staticmethod
    def _current_windows_user() -> str:
        domain = os.environ.get("USERDOMAIN", "").strip()
        username = os.environ.get("USERNAME", "").strip() or getpass.getuser()
        return f"{domain}\\{username}" if domain else username

    def _task_exists(self, name: str) -> bool:
        result = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0

    def _delete_task(self, name: str) -> None:
        if self._task_exists(name):
            self._run_schtasks(["/Delete", "/F", "/TN", name])

    def _delete_legacy_task_best_effort(self, name: str) -> None:
        """Clean up old task names without blocking settings on access errors."""
        if not self._task_exists(name):
            return
        subprocess.run(
            ["schtasks.exe", "/Delete", "/F", "/TN", name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _run_schtasks(self, arguments: list[str]) -> None:
        result = subprocess.run(
            ["schtasks.exe", *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "Unknown Task Scheduler error").strip()
            raise RuntimeError(details)

    def _require_windows(self) -> None:
        if not self.supported:
            raise RuntimeError("Windows startup integration is only available on Windows.")
