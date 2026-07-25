from __future__ import annotations

import sys
from pathlib import Path


def _application_root() -> Path:
    """Return the persistent folder containing the EXE or source project."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _application_root()
CONFIG_DIR = PROJECT_ROOT / "config"
LOG_DIR = PROJECT_ROOT / "logs"
BACKUP_RULES_PATH = CONFIG_DIR / "backup_rules.json"
SERVERS_CONFIG_PATH = CONFIG_DIR / "servers.json"
APP_SETTINGS_PATH = CONFIG_DIR / "settings.json"


def ensure_runtime_directories() -> None:
    """Create application-owned directories used at runtime."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
