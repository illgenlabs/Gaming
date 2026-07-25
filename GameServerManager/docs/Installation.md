# Installation and Build

Game Server Manager is designed for Windows 11 and can be run either from Python source or as a single executable.

## Run from source

### Requirements

- Windows 11
- Python 3 for Windows
- Tkinter support
- PowerShell

Install the runtime dependency:

```powershell
py -m pip install -r requirements.txt
```

Start the application:

```powershell
py main.py
```

The source-project directory acts as the application root. Runtime configuration and logs are stored below that directory.

## Build a portable executable

From the project root:

```powershell
.\build.ps1
```

The script:

1. Upgrades pip.
2. Installs `requirements.txt`.
3. Installs or upgrades PyInstaller.
4. Removes previous build output.
5. Creates a one-file, windowed executable with `app.ico`.

Output:

```text
dist\GameServerManager.exe
```

For a visible diagnostic console:

```powershell
.\build.ps1 -Console -Clean
```

## PowerShell execution policy

When Windows blocks local scripts, run the following in the current PowerShell session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then run:

```powershell
.\build.ps1
```

The `Process` scope only affects the current PowerShell session.

## Portable deployment

Place the built executable in a writable folder, for example:

```text
D:\GameServerManager\GameServerManager.exe
```

On first use, the application creates or uses folders such as:

```text
D:\GameServerManager\config
D:\GameServerManager\logs
D:\GameServerManager\servers
D:\GameServerManager\backups
```

No fixed installation directory is required.

### Moving the manager

To move the portable installation:

1. Stop all servers managed by the application.
2. Exit Game Server Manager.
3. Move the complete application folder, including `config` and any relative `servers` or `backups` folders.
4. Start the executable from its new location.
5. Open Settings and save once if Windows autostart or scheduled maintenance was enabled, so Windows entries point to the new executable path.

Absolute server or backup paths stored in Settings are not automatically converted when folders are moved separately.

## Windows autostart

The manager can register itself in the current user's Startup folder. Administrator rights should not be required for this user-level startup entry.

Two independent options exist:

- Start Game Server Manager after Windows login.
- Start the active game server after the manager starts.

Enable both options when a server should automatically return after a Windows restart.

## Daily maintenance

Daily maintenance is registered as a user-specific Windows scheduled task. The user must be logged in and the computer must be awake because the game-server console remains attached to the desktop application.

## Updating the application

Before replacing the executable:

1. Stop managed servers.
2. Exit the application.
3. Keep the `config` directory and backups.
4. Replace `GameServerManager.exe` with the new build.
5. Start it and review Settings and health checks.

Create a copy of the portable application folder before major updates.
