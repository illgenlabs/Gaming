from __future__ import annotations
import re
from pathlib import Path
from detectors.base_detector import BaseDetector
from models import ACTIONS, HealthCheck, ServerInfo


class ValheimDetector(BaseDetector):
    def can_handle(self, path: Path) -> bool:
        return (path / "valheim_server.exe").is_file()

    def detect(self, path: Path) -> ServerInfo:
        scripts = self._scripts(path)
        savedir = self._savedir(path, scripts.get("start", ""))
        backups = [savedir] if savedir else []
        checks = [
            HealthCheck("ok", "Valheim Dedicated Server detected."),
            HealthCheck("ok" if scripts["start"] else "warning", f"Start script: {scripts['start'] or 'not configured'}"),
            HealthCheck("info", "Valheim is stopped by terminating the exact managed process tree."),
        ]
        if savedir:
            checks.append(HealthCheck("ok" if (path / savedir).exists() else "info", f"Portable save directory: {savedir}"))
        else:
            checks.append(HealthCheck("warning", "No portable -savedir inside the server folder was detected. Configure -savedir for automatic backups."))
        detected = ["valheim_server.exe"] + [x for x in scripts.values() if x]
        return ServerInfo("", path.name, "valheim", str(path), scripts, False, detected,
                          {"Executable": "valheim_server.exe", "Save data": savedir or "External/default Valheim profile"},
                          [], [savedir] if savedir else [], backups, checks)

    @staticmethod
    def _scripts(path: Path) -> dict[str, str]:
        names = {p.name.casefold(): p.name for p in path.iterdir() if p.is_file()}
        choices = {
            "start": ("start_headless_server.bat", "start_valheim_server.bat", "start_server.bat", "start.bat"),
            "stop": ("stop.bat", "shutdown.bat"),
            "restart": ("restart.bat", "reboot.bat"),
            "update": ("update.bat", "update_server.bat", "update-valheim.bat", "server_update.bat"),
        }
        return {a: next((names[n.casefold()] for n in choices[a] if n.casefold() in names), "") for a in ACTIONS}

    @staticmethod
    def _savedir(path: Path, start_script: str) -> str:
        if not start_script:
            return ""
        script = path / start_script
        try:
            text = script.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return ""
        match = re.search(r'-savedir\s+(?:"([^"]+)"|([^\s\r\n]+))', text, re.IGNORECASE)
        if not match:
            return ""
        raw = (match.group(1) or match.group(2) or "").strip().replace("%SERVER_ROOT%", str(path))
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (path / candidate).resolve()
        try:
            return candidate.relative_to(path.resolve()).as_posix()
        except ValueError:
            return ""
