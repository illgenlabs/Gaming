from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.backup_manager import BackupManager, BackupRecord, ProgressCallback
from core.process_manager import ProcessManager
from core.server_types import supports_automatic_update
from models import ServerInfo


PAPER_API_ROOT = "https://fill.papermc.io/v3/projects"
PURPUR_API_ROOT = "https://api.purpurmc.org/v2/purpur"
FABRIC_API_ROOT = "https://meta.fabricmc.net/v2/versions"
VANILLA_MANIFEST_URL = (
    "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
)
USER_AGENT = "GameServerManager/0.4 (local Windows desktop application)"
NETWORK_TIMEOUT_SECONDS = 30
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ServerRelease:
    software: str
    minecraft_version: str
    build: str
    file_name: str
    download_url: str
    checksum: str = ""
    checksum_algorithm: str = "sha256"
    size: int = 0
    source: str = ""

    @property
    def display_name(self) -> str:
        suffix = f" {self.build}" if self.build else ""
        return f"{self.software} {self.minecraft_version}{suffix}".strip()


class UpdateManager:
    """Creates a safety backup and installs stable Minecraft server updates."""

    def __init__(self, backups: BackupManager, processes: ProcessManager) -> None:
        self.backups = backups
        self.processes = processes

    @staticmethod
    def supports_automatic_update(server: ServerInfo) -> bool:
        return supports_automatic_update(server.server_type)

    def update_server(
        self,
        server: ServerInfo,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[BackupRecord | None, int, str]:
        if self.processes.is_running(server.id):
            raise RuntimeError("The server must be stopped before updating.")

        update_script = server.action_scripts.get("update", "").strip()

        if self.supports_automatic_update(server):
            release = self._get_latest_release(server.server_type)
            backup, code, output = self._install_release(
                server, release, progress_callback
            )

            if update_script:
                if backup is None:
                    backup = self.backups.create_backup(
                        server=server,
                        backup_type="server_update",
                        reason="Automatisches Backup vor individuellem Updateskript",
                        metadata={
                            "action": "server_update",
                            "method": "plugin_update_script",
                            "server_software_current": True,
                        },
                        progress_callback=progress_callback,
                    )
                script_code, script_output = self.processes.update(server)
                combined = (
                    f"{output}\n\nIndividuelles Updateskript:\n{script_output}"
                ).strip()
                return backup, script_code, combined

            return backup, code, output

        if update_script:
            backup = self.backups.create_backup(
                server=server,
                backup_type="server_update",
                reason="Automatic backup before server update",
                metadata={"action": "server_update", "method": "script"},
                progress_callback=progress_callback,
            )
            code, output = self.processes.update(server)
            return backup, code, output

        raise RuntimeError(
            "No direct stable download is available for this server type. "
            "Configure an individual update script."
        )

    def _get_latest_release(self, server_type: str) -> ServerRelease:
        if server_type == "minecraft_paper":
            return self._get_papermc_release("paper", "Paper")
        if server_type == "minecraft_folia":
            return self._get_papermc_release("folia", "Folia")
        if server_type == "minecraft_purpur":
            return self._get_purpur_release()
        if server_type == "minecraft_vanilla":
            return self._get_vanilla_release()
        if server_type == "minecraft_fabric":
            return self._get_fabric_release()
        raise RuntimeError(f"Unbekannter automatischer Servertyp: {server_type}")

    def _get_papermc_release(self, project: str, software: str) -> ServerRelease:
        root = f"{PAPER_API_ROOT}/{project}"
        project_data = self._request_json(root, software)
        versions = self._extract_papermc_versions(project_data, software)

        for version in versions:
            builds = self._request_json(f"{root}/versions/{version}/builds", software)
            if not isinstance(builds, list):
                continue
            stable = [
                item
                for item in builds
                if isinstance(item, dict)
                and str(item.get("channel", "")).upper() == "STABLE"
            ]
            if not stable:
                continue
            stable.sort(
                key=lambda item: int(item.get("id", item.get("number", 0))),
                reverse=True,
            )
            build = stable[0]
            downloads = build.get("downloads")
            download = downloads.get("server:default") if isinstance(downloads, dict) else None
            if not isinstance(download, dict):
                continue
            checksums = download.get("checksums")
            sha256 = checksums.get("sha256", "") if isinstance(checksums, dict) else ""
            url = str(download.get("url", ""))
            name = str(download.get("name", ""))
            build_number = int(build.get("id", build.get("number", 0)))
            if url and name and sha256 and build_number > 0:
                return ServerRelease(
                    software=software,
                    minecraft_version=version,
                    build=f"Build {build_number}",
                    file_name=name,
                    download_url=url,
                    checksum=str(sha256),
                    checksum_algorithm="sha256",
                    size=int(download.get("size", 0) or 0),
                    source="papermc_downloads_service",
                )

        raise RuntimeError(f"{software} meldet derzeit keinen stabilen Build.")

    def _get_purpur_release(self) -> ServerRelease:
        project = self._request_json(PURPUR_API_ROOT, "Purpur")
        versions = project.get("versions") if isinstance(project, dict) else None
        if not isinstance(versions, list) or not versions:
            raise RuntimeError("Purpur reported no available versions.")

        for version in sorted(map(str, versions), key=self._version_key, reverse=True):
            detail = self._request_json(f"{PURPUR_API_ROOT}/{version}", "Purpur")
            builds = detail.get("builds") if isinstance(detail, dict) else None
            latest = builds.get("latest") if isinstance(builds, dict) else None
            if latest is None:
                continue
            build = str(latest)
            return ServerRelease(
                software="Purpur",
                minecraft_version=version,
                build=f"Build {build}",
                file_name=f"purpur-{version}-{build}.jar",
                download_url=f"{PURPUR_API_ROOT}/{version}/{build}/download",
                source="purpur_downloads_api",
            )

        raise RuntimeError("Purpur currently reports no available build.")

    def _get_vanilla_release(self) -> ServerRelease:
        manifest = self._request_json(VANILLA_MANIFEST_URL, "Mojang")
        latest = manifest.get("latest") if isinstance(manifest, dict) else None
        release_version = latest.get("release") if isinstance(latest, dict) else None
        versions = manifest.get("versions") if isinstance(manifest, dict) else None
        if not release_version or not isinstance(versions, list):
            raise RuntimeError("Mojang hat keine aktuelle stabile Version gemeldet.")

        version_url = next(
            (
                str(item.get("url"))
                for item in versions
                if isinstance(item, dict) and item.get("id") == release_version
            ),
            "",
        )
        if not version_url:
            raise RuntimeError("The metadata for the current Vanilla version is missing.")

        version_data = self._request_json(version_url, "Mojang")
        downloads = version_data.get("downloads") if isinstance(version_data, dict) else None
        server_download = downloads.get("server") if isinstance(downloads, dict) else None
        if not isinstance(server_download, dict):
            raise RuntimeError("Mojang does not provide a server JAR for this version.")

        url = str(server_download.get("url", ""))
        sha1 = str(server_download.get("sha1", ""))
        if not url or not sha1:
            raise RuntimeError("The Vanilla download metadata is incomplete.")

        return ServerRelease(
            software="Vanilla",
            minecraft_version=str(release_version),
            build="Stable",
            file_name=f"minecraft_server.{release_version}.jar",
            download_url=url,
            checksum=sha1,
            checksum_algorithm="sha1",
            size=int(server_download.get("size", 0) or 0),
            source="mojang_version_manifest",
        )

    def _get_fabric_release(self) -> ServerRelease:
        games = self._request_json(f"{FABRIC_API_ROOT}/game", "Fabric")
        if not isinstance(games, list):
            raise RuntimeError("Fabric hat keine Minecraft-Versionen gemeldet.")
        stable_games = [
            str(item.get("version"))
            for item in games
            if isinstance(item, dict) and item.get("stable") is True and item.get("version")
        ]
        if not stable_games:
            raise RuntimeError("Fabric meldet keine stabile Minecraft-Version.")
        game_version = sorted(stable_games, key=self._version_key, reverse=True)[0]

        loaders = self._request_json(
            f"{FABRIC_API_ROOT}/loader/{game_version}", "Fabric"
        )
        if not isinstance(loaders, list) or not loaders:
            raise RuntimeError("Fabric reports no loader for the current version.")
        stable_loaders = [
            item
            for item in loaders
            if isinstance(item, dict)
            and isinstance(item.get("loader"), dict)
            and item["loader"].get("stable") is True
        ]
        selected_loader = (stable_loaders or loaders)[0]
        loader_version = str(selected_loader.get("loader", {}).get("version", ""))
        if not loader_version:
            raise RuntimeError("The Fabric loader metadata is incomplete.")

        installers = self._request_json(f"{FABRIC_API_ROOT}/installer", "Fabric")
        if not isinstance(installers, list) or not installers:
            raise RuntimeError("Fabric meldet keinen Installer.")
        stable_installers = [
            item for item in installers if isinstance(item, dict) and item.get("stable") is True
        ]
        installer = (stable_installers or installers)[0]
        installer_version = str(installer.get("version", ""))
        if not installer_version:
            raise RuntimeError("The Fabric installer metadata is incomplete.")

        file_name = (
            f"fabric-server-mc.{game_version}-loader.{loader_version}-"
            f"launcher.{installer_version}.jar"
        )
        url = (
            f"{FABRIC_API_ROOT}/loader/{game_version}/{loader_version}/"
            f"{installer_version}/server/jar"
        )
        return ServerRelease(
            software="Fabric",
            minecraft_version=game_version,
            build=f"Loader {loader_version}",
            file_name=file_name,
            download_url=url,
            source="fabric_meta_api",
        )

    def _install_release(
        self,
        server: ServerInfo,
        release: ServerRelease,
        progress_callback: ProgressCallback | None,
    ) -> tuple[BackupRecord | None, int, str]:
        server_path = Path(server.path).expanduser().resolve()
        target_jar = self._detect_target_jar(server, server_path)
        temporary = target_jar.with_name(
            f".{target_jar.name}.{uuid.uuid4().hex}.download.tmp"
        )

        try:
            downloaded_hash = self._download_release(release, temporary)
            if target_jar.is_file():
                current_hash = self._file_hash(target_jar, release.checksum_algorithm)
                if current_hash.casefold() == downloaded_hash.casefold():
                    return None, 0, f"The server is already up to date.\n{release.display_name}"

            backup = self.backups.create_backup(
                server=server,
                backup_type="server_update",
                reason=f"Automatic backup before updating to {release.display_name}",
                metadata={
                    "action": "server_update",
                    "method": release.source,
                    "software": release.software,
                    "new_minecraft_version": release.minecraft_version,
                    "new_build": release.build,
                    "download_file": release.file_name,
                    "download_checksum": downloaded_hash,
                    "checksum_algorithm": release.checksum_algorithm,
                },
                progress_callback=progress_callback,
            )
            os.replace(temporary, target_jar)
        finally:
            temporary.unlink(missing_ok=True)

        return backup, 0, f"{release.display_name} wurde installiert.\nZiel: {target_jar}"

    def _download_release(self, release: ServerRelease, target: Path) -> str:
        request = Request(release.download_url, headers={"User-Agent": USER_AGENT})
        algorithm = release.checksum_algorithm or "sha256"
        digest = hashlib.new(algorithm)
        downloaded = 0

        try:
            with urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                with target.open("wb") as output:
                    while True:
                        chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        output.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
        except (HTTPError, URLError, OSError) as exc:
            raise RuntimeError(
                f"{release.software} could not be downloaded:\n{exc}"
            ) from exc

        if release.size and downloaded != release.size:
            raise RuntimeError(
                f"The {release.software} download is incomplete. "
                f"Erwartet: {release.size} Bytes, erhalten: {downloaded} Bytes."
            )

        actual_hash = digest.hexdigest()
        if release.checksum and actual_hash.casefold() != release.checksum.casefold():
            raise RuntimeError(
                f"The {algorithm.upper()} checksum of the {release.software} download "
                "does not match. The existing server JAR was not changed."
            )

        self._validate_jar(target, release.software)
        return actual_hash

    @staticmethod
    def _validate_jar(path: Path, software: str) -> None:
        try:
            if path.stat().st_size < 100_000:
                raise RuntimeError("The downloaded file is unusually small.")
            with zipfile.ZipFile(path) as archive:
                if archive.testzip() is not None:
                    raise RuntimeError("The downloaded JAR archive is damaged.")
                if "META-INF/MANIFEST.MF" not in archive.namelist():
                    raise RuntimeError("The downloaded file is not a valid JAR.")
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise RuntimeError(
                f"The downloaded {software}-server JAR is invalid: {exc}"
            ) from exc

    def _request_json(self, url: str, provider: str) -> Any:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"{provider}-Anfrage fehlgeschlagen (HTTP {exc.code}).") from exc
        except (URLError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"{provider} is unavailable:\n{exc}") from exc

    @staticmethod
    def _extract_papermc_versions(project: Any, software: str) -> list[str]:
        if not isinstance(project, dict):
            raise RuntimeError(f"{software} returned an invalid project response.")
        grouped = project.get("versions")
        if not isinstance(grouped, dict):
            raise RuntimeError(f"In der {software}-Antwort fehlen die Versionen.")
        versions = {
            str(version)
            for group in grouped.values()
            if isinstance(group, list)
            for version in group
        }
        return sorted(versions, key=UpdateManager._version_key, reverse=True)

    @staticmethod
    def _version_key(version: str) -> tuple[tuple[int, object], ...]:
        parts = re.findall(r"\d+|[A-Za-z]+", version)
        return tuple(
            (1, int(part)) if part.isdigit() else (0, part.casefold())
            for part in parts
        )

    @staticmethod
    def _file_hash(path: Path, algorithm: str = "sha256") -> str:
        digest = hashlib.new(algorithm)
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(DOWNLOAD_CHUNK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _detect_target_jar(self, server: ServerInfo, server_path: Path) -> Path:
        start_script = server.action_scripts.get("start", "").strip()
        if start_script:
            script_path = Path(start_script)
            if not script_path.is_absolute():
                script_path = server_path / script_path
            if script_path.is_file():
                text = script_path.read_text(encoding="utf-8-sig", errors="replace")
                match = re.search(
                    r"(?i)(?:^|\s)-jar\s+(?:\"([^\"]+)\"|'([^']+)'|([^\s&|<>]+))",
                    text,
                )
                if match:
                    jar_name = next(group for group in match.groups() if group)
                    jar_path = Path(jar_name)
                    if not jar_path.is_absolute():
                        jar_path = server_path / jar_path
                    return jar_path.resolve()

        jars = sorted(
            (
                path
                for path in server_path.iterdir()
                if path.is_file() and path.suffix.casefold() == ".jar"
            ),
            key=lambda path: path.name.casefold(),
        )
        tokens = {
            "minecraft_paper": "paper",
            "minecraft_folia": "folia",
            "minecraft_purpur": "purpur",
            "minecraft_fabric": "fabric",
            "minecraft_vanilla": "server",
        }
        token = tokens.get(server.server_type, "")
        preferred = [path for path in jars if token and token in path.name.casefold()]
        candidates = preferred or jars
        if len(candidates) == 1:
            return candidates[0].resolve()
        if not candidates:
            raise RuntimeError("No server JAR was found in the server folder.")
        names = "\n".join(f"• {path.name}" for path in candidates)
        raise RuntimeError(
            "The active server JAR could not be determined unambiguously. "
            "Check the -jar entry in the start script.\n\nFiles found:\n"
            f"{names}"
        )
