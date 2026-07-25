# Supported Server Types

Game Server Manager manages existing server installations selected by the user. Detection is intentionally conservative and does not install, download, or copy server software.

## Definition and detector separation

Supported server types are registered centrally in `core/server_types.py`. A `ServerTypeDefinition` contains only shared, declarative behavior:

- Display name and broad server family
- Shutdown strategy and optional console command
- Capability flags for automatic updates, plugins, and worlds
- Static required and optional default backup paths

Game-specific detection and parsing remain in `detectors/` and `minecraft/`. Detectors identify an installation, read its configuration, discover scripts, and resolve dynamic data such as Minecraft worlds or a Valheim `-savedir`. Process, update, backup, and UI code consume the central definition instead of duplicating server-name checks.

This separation keeps server metadata centralized without moving executable behavior into external configuration files.

## Minecraft Java Edition

Recognized families include:

- Paper
- Folia
- Purpur
- Vanilla
- Fabric
- Forge
- NeoForge
- Spigot
- Bukkit
- Generic Minecraft Java

Common behavior:

- Safe console shutdown with `stop`
- Automatic world detection
- Integrated console input
- Player-list polling
- Plugins and Worlds tabs where supported by the detected type

Automatic stable updates are currently available only for the server families marked as update-capable in the application, including Paper, Folia, Purpur, Vanilla, and Fabric. Other variants require an update script.

## Minecraft Bedrock Dedicated Server

Detection uses files such as:

```text
bedrock_server.exe
server.properties
worlds/
```

Behavior:

- Safe console shutdown with `stop`
- Automatic handling of the `worlds` directory
- Integrated console while started by the manager
- No Java plugin handling

## Windrose Dedicated Server

Windrose is detected from its dedicated-server executable and expected directory layout.

Behavior:

- Direct launch with output redirected to the integrated console
- No separate visible server console
- Stop by terminating the exact managed PID and its process tree
- Default backup selection:

  ```text
  R5/Saved/SaveProfiles/Default
  R5/ServerDescription.json
  ```

  Some layouts may use a root-level `ServerDescription.json`.

## Factorio Dedicated Server

Detection uses `factorio.exe` and related server files.

Behavior:

- Safe console shutdown with `/quit`
- Default backup handling for `saves` and common JSON configuration files
- Common start and update script names are detected where present

## Valheim Dedicated Server

Detection uses `valheim_server.exe` and common script names.

Behavior:

- Stop by terminating the exact managed PID and its process tree
- A portable backup selection is created when the start script defines `-savedir` below the selected server directory
- When save data remains in the default user-profile location, the manager reports that a portable backup path could not be selected automatically

For predictable portable backups, configure Valheim with a `-savedir` inside the managed server folder.

## ARK: Survival Evolved

Detection uses the matching server executable below the expected `ShooterGame/Binaries/Win64` layout.

Behavior:

- Stop by terminating the exact managed PID and its process tree
- Default backup root:

  ```text
  ShooterGame/Saved
  ```

## ARK: Survival Ascended

Detection distinguishes the Ascended executable and uses the same conservative saved-data root:

```text
ShooterGame/Saved
```

Stop behavior uses the exact managed PID and its process tree.

## Generic Server

Use Generic Server when no dedicated detector applies.

The user is responsible for selecting:

- Start script
- Stop script
- Update script, when required
- Backup files and directories

Restart remains Stop followed by Start.

## Script requirements

Scripts are not copied into Game Server Manager. They must remain inside the selected server directory. The manager stores their relative paths where possible.

A script that starts a server should keep the launched process attached to the manager. Scripts that detach into another terminal or launcher may prevent console integration and reliable process tracking.

## Detection safety

Detection only inspects the selected folder. It should not modify server files. Always review the detected type and health checks before starting maintenance or updates on a newly added server.
