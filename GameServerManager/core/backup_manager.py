from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable
from uuid import uuid4

from core.paths import BACKUP_RULES_PATH, PROJECT_ROOT, ensure_runtime_directories
from models import ServerInfo

ProgressCallback = Callable[[str, int, int], None]


@dataclass(frozen=True)
class BackupRecord:
    id: str
    backup_type: str
    created: str
    server_id: str
    server_name: str
    reason: str
    archive_path: str
    size_bytes: int
    file_count: int

    @property
    def created_display(self) -> str:
        try:
            value = datetime.fromisoformat(self.created)
            return value.strftime("%d.%m.%Y %H:%M")
        except ValueError:
            return self.created


class BackupManager:
    """Creates filtered ZIP backups with a JSON manifest."""

    VALID_TYPES = {"full", "world", "plugin_update", "server_update", "manual"}
    MAX_STORAGE_PER_SERVER = 50 * 1024 ** 3
    MIN_FULL_BACKUPS = 2

    def __init__(self, backup_root: Path | None = None) -> None:
        ensure_runtime_directories()
        self.backup_root = (backup_root or (PROJECT_ROOT / "backups")).resolve()
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.rules = self._load_rules()

    def create_backup(
        self,
        server: ServerInfo,
        backup_type: str = "full",
        reason: str = "Manual backup",
        metadata: dict[str, object] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> BackupRecord:
        if backup_type not in self.VALID_TYPES:
            raise ValueError(f"Unknown backup type: {backup_type}")

        source_root = Path(server.path).resolve()
        if not source_root.is_dir():
            raise ValueError("The server folder was not found.")

        files = list(self._collect_files(source_root, server, backup_type))
        backup_id = str(uuid4())
        created = datetime.now().astimezone().isoformat(timespec="seconds")
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_name = self._safe_filename(server.name)
        server_dir = self.backup_root / server.id
        server_dir.mkdir(parents=True, exist_ok=True)
        archive_path = server_dir / f"{stamp}_{backup_type}_{safe_name}_{backup_id[:8]}.zip"
        temp_path = archive_path.with_suffix(".zip.tmp")

        manifest_files: list[dict[str, object]] = []
        try:
            with zipfile.ZipFile(
                temp_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
                allowZip64=True,
            ) as archive:
                total = len(files)
                for index, file_path in enumerate(files, start=1):
                    relative = file_path.relative_to(source_root).as_posix()
                    if progress_callback:
                        progress_callback(relative, index, total)
                    archive.write(file_path, arcname=f"server/{relative}")
                    stat = file_path.stat()
                    manifest_files.append(
                        {
                            "path": relative,
                            "size": stat.st_size,
                            "sha256": self._sha256(file_path),
                        }
                    )

                manifest = {
                    "version": 1,
                    "id": backup_id,
                    "backup_type": backup_type,
                    "reason": reason,
                    "created": created,
                    "server": {
                        "id": server.id,
                        "name": server.name,
                        "type": server.server_type,
                        "source_path": str(source_root),
                    },
                    "metadata": metadata or {},
                    "file_count": len(manifest_files),
                    "files": manifest_files,
                }
                archive.writestr(
                    "backup.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                )

            temp_path.replace(archive_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        self.apply_retention(server.id, backup_type)
        self.enforce_storage_limit(server.id)
        return self.read_record(archive_path)

    def list_backups(self, server_id: str | None = None) -> list[BackupRecord]:
        roots = [self.backup_root / server_id] if server_id else [self.backup_root]
        records: list[BackupRecord] = []
        for root in roots:
            if not root.exists():
                continue
            for archive_path in root.rglob("*.zip"):
                try:
                    records.append(self.read_record(archive_path))
                except (OSError, ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
                    continue
        return sorted(records, key=lambda item: item.created, reverse=True)

    def read_record(self, archive_path: Path) -> BackupRecord:
        with zipfile.ZipFile(archive_path, "r") as archive:
            manifest = json.loads(archive.read("backup.json").decode("utf-8"))
        server = manifest.get("server", {})
        return BackupRecord(
            id=str(manifest["id"]),
            backup_type=str(manifest["backup_type"]),
            created=str(manifest["created"]),
            server_id=str(server.get("id", "")),
            server_name=str(server.get("name", "")),
            reason=str(manifest.get("reason", "")),
            archive_path=str(archive_path),
            size_bytes=archive_path.stat().st_size,
            file_count=int(manifest.get("file_count", 0)),
        )

    def delete_backup(self, record: BackupRecord) -> None:
        path = Path(record.archive_path).resolve()
        try:
            path.relative_to(self.backup_root)
        except ValueError as exc:
            raise ValueError("The backup is outside the backup folder.") from exc
        path.unlink(missing_ok=False)

    def apply_retention(self, server_id: str, backup_type: str) -> None:
        keep = int(self.rules.get("retention", {}).get(backup_type, 0) or 0)
        if keep <= 0:
            return
        matching = [item for item in self.list_backups(server_id) if item.backup_type == backup_type]
        for old_record in matching[keep:]:
            Path(old_record.archive_path).unlink(missing_ok=True)

    def storage_used(self, server_id: str) -> int:
        return sum(record.size_bytes for record in self.list_backups(server_id))

    def enforce_storage_limit(self, server_id: str) -> list[BackupRecord]:
        records = self.list_backups(server_id)
        total = sum(item.size_bytes for item in records)
        if total <= self.MAX_STORAGE_PER_SERVER:
            return []
        removed: list[BackupRecord] = []
        full_records = [item for item in records if item.backup_type == "full"]
        protected_full_ids = {item.id for item in full_records[:self.MIN_FULL_BACKUPS]}
        priority = {"world": 0, "plugin_update": 1, "manual": 2, "server_update": 3, "full": 4}
        candidates = sorted(
            (item for item in records if item.id not in protected_full_ids),
            key=lambda item: (priority.get(item.backup_type, 2), item.created),
        )
        for record in candidates:
            if total <= self.MAX_STORAGE_PER_SERVER:
                break
            Path(record.archive_path).unlink(missing_ok=True)
            total -= record.size_bytes
            removed.append(record)
        return removed

    def _collect_files(
        self,
        source_root: Path,
        server: ServerInfo,
        backup_type: str,
    ) -> Iterable[Path]:
        world_roots = {PurePosixPath(item).parts[0] for item in server.worlds if item}
        if not world_roots:
            world_roots = {"world", "world_nether", "world_the_end"}

        custom_patterns = [item.replace("\\", "/").strip().lstrip("./") for item in server.backup_paths if item.strip()]
        use_custom_selection = not server.server_type.startswith("minecraft_") and backup_type in {"full", "manual", "server_update"}
        if use_custom_selection and not custom_patterns:
            raise ValueError(
                "No backup files are configured for this non-Minecraft server. "
                "Define relative files or folders in the Scripts tab first."
            )

        for path in source_root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(source_root).as_posix()
            if not self._included(relative):
                continue
            parts = PurePosixPath(relative).parts
            top = parts[0] if parts else ""

            if use_custom_selection and not any(self._path_selected(relative, pattern) for pattern in custom_patterns):
                continue
            if backup_type == "world" and top not in world_roots:
                continue
            if backup_type == "plugin_update" and top != "plugins":
                continue
            yield path

    @classmethod
    def _path_selected(cls, relative: str, pattern: str) -> bool:
        normalized = relative.replace("\\", "/")
        selected = pattern.rstrip("/")
        if not selected:
            return False
        return (
            normalized == selected
            or normalized.startswith(selected + "/")
            or cls._matches(normalized, selected)
            or cls._matches(normalized, selected + "/**")
        )

    def _included(self, relative: str) -> bool:
        normalized = relative.replace("\\", "/")
        includes = self.rules.get("include", ["**"])
        excludes = self.rules.get("exclude", [])
        included = any(self._matches(normalized, pattern) for pattern in includes)
        excluded = any(self._matches(normalized, pattern) for pattern in excludes)
        return included and not excluded

    @staticmethod
    def _matches(path: str, pattern: str) -> bool:
        normalized_pattern = str(pattern).replace("\\", "/")
        # PurePath.match handles ** more naturally; fnmatch covers simple legacy patterns.
        return PurePosixPath(path).match(normalized_pattern) or fnmatch.fnmatch(path, normalized_pattern)

    def _load_rules(self) -> dict[str, object]:
        defaults: dict[str, object] = {
            "version": 1,
            "include": ["**"],
            "exclude": [
                "logs/**",
                ".paper-remapped/**",
                "**/cache/**",
                "**/tmp/**",
                "**/temp/**",
                "**/*.tmp",
                "**/*.lock",
                "**/session.lock",
            ],
            "retention": {
                "full": 5,
                "world": 20,
                "plugin_update": 10,
                "server_update": 5,
                "manual": 10,
            },
        }
        try:
            with BACKUP_RULES_PATH.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
            if isinstance(loaded, dict):
                defaults.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
        return defaults

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _safe_filename(value: str) -> str:
        invalid = '<>:"/\\|?*'
        cleaned = "".join("_" if char in invalid else char for char in value).strip()
        return cleaned or "server"


def format_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size_bytes} B"
