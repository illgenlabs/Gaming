# Game Server Manager

A portable Windows desktop application for managing existing dedicated game servers from one interface.

Game Server Manager can start, stop, restart, update, monitor, back up, and maintain multiple local game servers. It is written in Python with Tkinter, stores its configuration in JSON files, and can be built as a single Windows executable.

> **Project status:** solid working baseline. The application is intended for local Windows server administration and currently focuses on simple, transparent operation rather than remote hosting or cloud management.

## Highlights

- Portable operation with no fixed installation directory
- Management of multiple existing server installations
- Integrated live console and command input
- Start, stop, restart, and update workflows
- Automatic and manual backups with retention rules
- Scheduled daily maintenance
- Optional Windows autostart
- Optional automatic restart of the active server after Windows login
- ntfy push notifications without SMTP credentials
- Structured health checks
- Traffic-light status directly in the server list
- Single-instance handling for scheduled actions
- JSON configuration; no database required

## Supported servers

| Server type | Detection | Console stop | Default backup handling |
|---|---:|---:|---:|
| Minecraft Java: Paper, Folia, Purpur, Vanilla, Fabric, Forge, NeoForge, Spigot, Bukkit | Yes | `stop` | Automatic world detection |
| Minecraft Bedrock Dedicated Server | Yes | `stop` | Automatic `worlds` handling |
| Windrose Dedicated Server | Yes | Managed PID/process tree | Automatic save-profile selection |
| Factorio Dedicated Server | Yes | `/quit` | `saves` and common configuration files |
| Valheim Dedicated Server | Yes | Managed PID/process tree | Portable `-savedir` detection |
| ARK: Survival Evolved | Yes | Managed PID/process tree | `ShooterGame/Saved` |
| ARK: Survival Ascended | Yes | Managed PID/process tree | `ShooterGame/Saved` |
| Generic server | Manual | Configurable stop script | User-defined selection |

The manager works with **existing server installations**. It does not download, install, or generate complete game servers.

## Portable layout

When built as an executable, the application uses the folder containing `GameServerManager.exe` as its persistent root.

```text
GameServerManager.exe
├── config/
├── logs/
├── servers/
└── backups/
```

The default server and backup directories are created relative to the executable. They can be changed in Settings. Moving the application folder also moves its portable configuration, provided the related folders are moved with it.

## Basic workflow

1. Start Game Server Manager.
2. Add an existing server directory.
3. Review the detected server type and health checks.
4. Select start, stop, and update scripts where required.
5. Start the server from the manager so its process and console can be tracked.
6. Configure backups, maintenance, autostart, and ntfy as needed.

Restart is always implemented as:

```text
Stop
↓
Start
```

There is no separate restart script.

## Scripts

The manager stores only script paths. Scripts remain inside the managed server directory and are never copied into the application.

- **Start script:** normally required, except where the manager launches the server executable directly.
- **Stop script:** optional for servers with a supported console stop command or managed-PID shutdown.
- **Update script:** optional; used for custom or unsupported update workflows.

Script paths should remain inside the corresponding server directory and are stored relative to that directory where possible.

## Backups

The backup system supports:

- Full backups
- World backups
- Plugin-update backups
- Server-update safety backups
- Manual backups
- SHA-256 checksums and manifests
- Count-based retention
- Per-server storage limits

Default retention values are documented in [docs/Backups.md](docs/Backups.md).

## Maintenance and autostart

The Settings dialog can configure:

- Starting Game Server Manager when the Windows user logs in
- Starting the currently active server after the manager starts
- Daily maintenance at a selected time

The two startup options are separate. This allows the manager to start automatically without necessarily starting a game server.

Daily maintenance follows the current active-server workflow and can stop, back up, update, and restart the server. See [docs/Maintenance.md](docs/Maintenance.md).

## ntfy notifications

Game Server Manager can send notifications through an ntfy server.

The minimal configuration is:

- Enable ntfy
- Keep `https://ntfy.sh` or enter a self-hosted ntfy URL
- Choose a long, unique topic
- Press **Test ntfy**
- Subscribe to the same topic in the ntfy app or browser

No SMTP credentials are required. Public ntfy topics act like addresses, so do not use short or guessable topic names and do not send sensitive data through a public topic.

## Server status

The server list uses a simple traffic-light indicator:

- 🟢 **Running**
- 🟡 **Update or manager operation in progress**
- 🔴 **Stopped**

## Requirements for source use

- Windows 11
- Python 3
- Tkinter, normally included with the standard Windows Python installer
- `psutil` for process and resource metrics

Install the Python dependency with:

```powershell
py -m pip install -r requirements.txt
```

## Building the executable

From the project root, run:

```powershell
.\build.ps1
```

The script installs the required build dependencies and creates:

```text
dist\GameServerManager.exe
```

For a diagnostic build with a visible console:

```powershell
.\build.ps1 -Console -Clean
```

More details are available in [docs/Installation.md](docs/Installation.md).

## Documentation

- [Installation and build](docs/Installation.md)
- [Supported server types](docs/ServerTypes.md)
- [Backups](docs/Backups.md)
- [Maintenance and autostart](docs/Maintenance.md)
- [Frequently asked questions](docs/FAQ.md)
- [Project changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## Project structure

```text
core/        Process, backup, update, settings, notification, and scheduler logic
detectors/   Detection for supported non-Java server types
minecraft/   Minecraft Java detection
models/      Shared data models
ui/          Tkinter interface
config/      JSON configuration and backup rules
main.py      Application entry point and single-instance control
build.ps1    PyInstaller one-file build
```

Runtime folders such as `logs`, `backups`, `build`, and `dist` are created when needed and should generally not be committed.

## Privacy

- No account is required.
- No telemetry is included.
- Configuration remains local.
- ntfy is optional and only sends notifications when enabled.

## Contributing

Bug reports, focused feature proposals, documentation improvements, and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a larger change.

## License

This project is licensed under the [MIT License](LICENSE).
