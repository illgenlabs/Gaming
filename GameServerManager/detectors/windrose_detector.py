from __future__ import annotations
from pathlib import Path
from detectors.base_detector import BaseDetector
from models import HealthCheck, ServerInfo


class WindroseDetector(BaseDetector):
    """Detects Windrose and its officially documented backup data."""

    @staticmethod
    def default_backup_paths(path: Path) -> list[str]:
        paths: list[str] = []
        save_root = Path("R5/Saved/SaveProfiles/Default")
        # Keep the documented save root even before the first world is generated.
        paths.append(save_root.as_posix())

        for candidate in (Path("R5/ServerDescription.json"), Path("ServerDescription.json")):
            if (path / candidate).is_file():
                paths.append(candidate.as_posix())

        # Some builds may place the file differently. Avoid duplicate entries.
        return list(dict.fromkeys(paths))

    def can_handle(self, path: Path) -> bool:
        root_names = {p.name.casefold() for p in path.iterdir()}
        r5 = path / "R5"
        r5_names = {p.name.casefold() for p in r5.iterdir()} if r5.is_dir() else set()
        return (
            "serverdescription.json" in root_names
            or "serverdescription.json" in r5_names
            or "worlddescription.json" in root_names
            or any("windrose" in name for name in root_names)
            or (r5 / "Saved" / "SaveProfiles").exists()
        )

    def detect(self, path: Path) -> ServerInfo:
        candidates = {
            "start": ("StartServerForeground.bat", "start.bat", "run.bat"),
            "stop": ("stop.bat", "shutdown.bat"),
            "restart": ("restart.bat", "reboot.bat"),
            "update": ("update.bat", "update_server.bat", "server_update.bat"),
        }
        names = {p.name.casefold(): p.name for p in path.iterdir() if p.is_file()}
        scripts = {
            action: next((names[name.casefold()] for name in choices if name.casefold() in names), "")
            for action, choices in candidates.items()
        }

        backup_paths = self.default_backup_paths(path)
        save_path = path / "R5" / "Saved" / "SaveProfiles" / "Default"
        config_candidates = [
            candidate for candidate in ("R5/ServerDescription.json", "ServerDescription.json")
            if (path / candidate).is_file()
        ]

        checks = [HealthCheck("ok", "Windrose Dedicated Server detected.")]
        checks.append(HealthCheck(
            "ok" if scripts["start"] else "error",
            f"Start script: {scripts['start'] or 'not configured'}",
        ))
        checks.append(HealthCheck(
            "ok" if scripts["stop"] else "warning",
            f"Stop script: {scripts['stop'] or 'not configured'}",
        ))
        checks.append(HealthCheck(
            "ok" if scripts["update"] else "warning",
            f"Update script: {scripts['update'] or 'not configured'}",
        ))
        checks.append(HealthCheck(
            "ok" if config_candidates else "warning",
            "Server configuration: " + (", ".join(config_candidates) if config_candidates else "ServerDescription.json not detected"),
        ))
        checks.append(HealthCheck(
            "ok" if save_path.exists() else "info",
            "Save data: R5/Saved/SaveProfiles/Default" + ("" if save_path.exists() else " (created after the server has generated a world)"),
        ))
        checks.append(HealthCheck(
            "ok",
            "Backup selection is configured automatically for Windrose saves and ServerDescription.json.",
        ))

        detected = sorted(
            {value for value in scripts.values() if value} | set(config_candidates) | {"R5/Saved/SaveProfiles/Default"},
            key=str.casefold,
        )
        return ServerInfo(
            id="",
            name=path.name,
            server_type="windrose",
            path=str(path),
            action_scripts=scripts,
            active=False,
            detected_files=detected,
            properties={
                "Save data": "R5/Saved/SaveProfiles/Default",
                "Server configuration": ", ".join(config_candidates) or "ServerDescription.json not detected",
            },
            plugins=[],
            worlds=[],
            backup_paths=backup_paths,
            health_checks=checks,
        )
