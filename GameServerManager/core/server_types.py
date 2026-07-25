from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ServerFamily(str, Enum):
    """Broad server family used by shared UI and feature logic."""

    GENERIC = "generic"
    MINECRAFT = "minecraft"
    STEAM = "steam"
    WINDROSE = "windrose"


class StopStrategy(str, Enum):
    """How the manager stops a server started by ProcessManager."""

    SCRIPT = "script"
    CONSOLE = "console"
    MANAGED_PROCESS = "managed_process"


@dataclass(frozen=True, slots=True)
class ServerTypeDefinition:
    """Central, declarative definition of a supported server type.

    Detection and game-specific parsing remain in the detector modules. Shared
    capabilities, shutdown behavior, labels, and static backup defaults live
    here so the UI and managers do not need server-name conditionals.
    """

    key: str
    display_name: str
    family: ServerFamily = ServerFamily.GENERIC
    stop_strategy: StopStrategy = StopStrategy.SCRIPT
    console_stop_command: str = ""
    automatic_update: bool = False
    plugins: bool = False
    worlds: bool = False
    default_backup_paths: tuple[str, ...] = ()
    optional_backup_paths: tuple[str, ...] = ()

    @property
    def is_minecraft(self) -> bool:
        return self.family == ServerFamily.MINECRAFT

    @property
    def supports_console_stop(self) -> bool:
        return self.stop_strategy == StopStrategy.CONSOLE

    @property
    def supports_managed_pid_stop(self) -> bool:
        return self.stop_strategy == StopStrategy.MANAGED_PROCESS

    @property
    def supports_automatic_update(self) -> bool:
        return self.automatic_update

    @property
    def supports_plugins(self) -> bool:
        return self.plugins

    @property
    def supports_worlds(self) -> bool:
        return self.worlds

    def backup_paths_for(self, server_root: Path) -> list[str]:
        """Return the static default backup selection for an installation.

        Required defaults are retained even before a server creates them.
        Optional defaults are included only when they currently exist.
        Dynamic selections, such as Minecraft worlds or Valheim ``-savedir``,
        remain the responsibility of their detector.
        """

        paths = list(self.default_backup_paths)
        paths.extend(
            relative_path
            for relative_path in self.optional_backup_paths
            if (server_root / relative_path).exists()
        )
        return list(dict.fromkeys(paths))


SERVER_TYPES: dict[str, ServerTypeDefinition] = {
    "minecraft_paper": ServerTypeDefinition(
        key="minecraft_paper", display_name="Minecraft (Paper)",
        family=ServerFamily.MINECRAFT, stop_strategy=StopStrategy.CONSOLE,
        console_stop_command="stop", automatic_update=True, plugins=True, worlds=True,
    ),
    "minecraft_folia": ServerTypeDefinition(
        key="minecraft_folia", display_name="Minecraft (Folia)",
        family=ServerFamily.MINECRAFT, stop_strategy=StopStrategy.CONSOLE,
        console_stop_command="stop", automatic_update=True, plugins=True, worlds=True,
    ),
    "minecraft_purpur": ServerTypeDefinition(
        key="minecraft_purpur", display_name="Minecraft (Purpur)",
        family=ServerFamily.MINECRAFT, stop_strategy=StopStrategy.CONSOLE,
        console_stop_command="stop", automatic_update=True, plugins=True, worlds=True,
    ),
    "minecraft_vanilla": ServerTypeDefinition(
        key="minecraft_vanilla", display_name="Minecraft (Vanilla)",
        family=ServerFamily.MINECRAFT, stop_strategy=StopStrategy.CONSOLE,
        console_stop_command="stop", automatic_update=True, worlds=True,
    ),
    "minecraft_fabric": ServerTypeDefinition(
        key="minecraft_fabric", display_name="Minecraft (Fabric)",
        family=ServerFamily.MINECRAFT, stop_strategy=StopStrategy.CONSOLE,
        console_stop_command="stop", automatic_update=True, plugins=True, worlds=True,
    ),
    "minecraft_forge": ServerTypeDefinition(
        key="minecraft_forge", display_name="Minecraft (Forge)",
        family=ServerFamily.MINECRAFT, stop_strategy=StopStrategy.CONSOLE,
        console_stop_command="stop", plugins=True, worlds=True,
    ),
    "minecraft_neoforge": ServerTypeDefinition(
        key="minecraft_neoforge", display_name="Minecraft (NeoForge)",
        family=ServerFamily.MINECRAFT, stop_strategy=StopStrategy.CONSOLE,
        console_stop_command="stop", plugins=True, worlds=True,
    ),
    "minecraft_spigot": ServerTypeDefinition(
        key="minecraft_spigot", display_name="Minecraft (Spigot)",
        family=ServerFamily.MINECRAFT, stop_strategy=StopStrategy.CONSOLE,
        console_stop_command="stop", plugins=True, worlds=True,
    ),
    "minecraft_bukkit": ServerTypeDefinition(
        key="minecraft_bukkit", display_name="Minecraft (Bukkit)",
        family=ServerFamily.MINECRAFT, stop_strategy=StopStrategy.CONSOLE,
        console_stop_command="stop", plugins=True, worlds=True,
    ),
    "minecraft_java": ServerTypeDefinition(
        key="minecraft_java", display_name="Minecraft (Java Edition)",
        family=ServerFamily.MINECRAFT, stop_strategy=StopStrategy.CONSOLE,
        console_stop_command="stop", worlds=True,
    ),
    "minecraft_bedrock": ServerTypeDefinition(
        key="minecraft_bedrock", display_name="Minecraft Bedrock Dedicated Server",
        family=ServerFamily.MINECRAFT, stop_strategy=StopStrategy.CONSOLE,
        console_stop_command="stop", worlds=True,
        default_backup_paths=("worlds",),
    ),
    "factorio": ServerTypeDefinition(
        key="factorio", display_name="Factorio Dedicated Server",
        family=ServerFamily.STEAM, stop_strategy=StopStrategy.CONSOLE,
        console_stop_command="/quit", worlds=True,
        default_backup_paths=("saves",),
        optional_backup_paths=(
            "config", "mods", "data/server-settings.json", "server-settings.json",
            "server-adminlist.json", "server-banlist.json", "server-whitelist.json",
        ),
    ),
    "valheim": ServerTypeDefinition(
        key="valheim", display_name="Valheim Dedicated Server",
        family=ServerFamily.STEAM, stop_strategy=StopStrategy.MANAGED_PROCESS,
        worlds=True,
    ),
    "ark_evolved": ServerTypeDefinition(
        key="ark_evolved", display_name="ARK: Survival Evolved Dedicated Server",
        family=ServerFamily.STEAM, stop_strategy=StopStrategy.MANAGED_PROCESS,
        default_backup_paths=("ShooterGame/Saved",),
    ),
    "ark_ascended": ServerTypeDefinition(
        key="ark_ascended", display_name="ARK: Survival Ascended Dedicated Server",
        family=ServerFamily.STEAM, stop_strategy=StopStrategy.MANAGED_PROCESS,
        default_backup_paths=("ShooterGame/Saved",),
    ),
    "windrose": ServerTypeDefinition(
        key="windrose", display_name="Windrose Dedicated Server",
        family=ServerFamily.WINDROSE, stop_strategy=StopStrategy.MANAGED_PROCESS,
        default_backup_paths=("R5/Saved/SaveProfiles/Default",),
        optional_backup_paths=("R5/ServerDescription.json", "ServerDescription.json"),
    ),
    "generic": ServerTypeDefinition(key="generic", display_name="Generic Server"),
}


def get_server_type(server_type: str) -> ServerTypeDefinition:
    key = str(server_type or "generic").strip() or "generic"
    definition = SERVER_TYPES.get(key)
    if definition is not None:
        return definition
    fallback_name = key.replace("_", " ").strip().title() or "Generic Server"
    return ServerTypeDefinition(key=key, display_name=fallback_name)


def get_server_type_name(server_type: str) -> str:
    return get_server_type(server_type).display_name


def is_minecraft_server(server_type: str) -> bool:
    return get_server_type(server_type).is_minecraft


def supports_console_stop(server_type: str) -> bool:
    return get_server_type(server_type).supports_console_stop


def get_console_stop_command(server_type: str) -> str:
    return get_server_type(server_type).console_stop_command or "stop"


def supports_automatic_update(server_type: str) -> bool:
    return get_server_type(server_type).supports_automatic_update


def supports_managed_pid_stop(server_type: str) -> bool:
    return get_server_type(server_type).supports_managed_pid_stop


# Compatibility alias for older UI code/configuration.
def supports_ctrl_break_stop(server_type: str) -> bool:
    return supports_managed_pid_stop(server_type)
