# Contributing to Game Server Manager

Thank you for considering a contribution.

The project values simple, portable, and understandable solutions. Changes should avoid unnecessary dependencies, fixed installation paths, copied server scripts, and server-specific logic inside unrelated UI code.

## Before opening an issue

Please check whether the problem is reproducible with the latest project state.

For bug reports, include:

- Windows version
- Python version or executable build used
- Server type
- Steps to reproduce
- Expected behavior
- Actual behavior
- Relevant log output with secrets and personal paths removed

Do not publish private ntfy topics, access tokens, server passwords, public IP addresses, or other credentials.

## Development setup

1. Install Python 3 for Windows with Tkinter support.
2. Clone or extract the repository.
3. Install dependencies:

   ```powershell
   py -m pip install -r requirements.txt
   ```

4. Run from source:

   ```powershell
   py main.py
   ```

5. Build the executable when required:

   ```powershell
   .\build.ps1 -Clean
   ```

## Design guidelines

- Keep the application portable.
- Resolve application-owned paths from the source project or running executable.
- Store user configuration in JSON.
- Keep scripts inside the managed server directory; store only their paths.
- Prefer capabilities and shared interfaces over repeated checks for a specific server name.
- Keep server detection conservative. A false “generic” result is safer than modifying the wrong installation.
- Stop the exact process started by the manager whenever possible.
- Do not add a separate restart script; restart is Stop followed by Start.
- Avoid blocking the Tkinter main thread with process, network, backup, or update work.
- Keep notification payloads free of secrets.
- Do not add telemetry.

## Adding a server type

A focused server integration normally includes:

1. A central type definition and capability flags in `core/server_types.py`.
2. A detector in `detectors/` or `minecraft/`.
3. Conservative start, stop, and update behavior.
4. Safe default backup selection where possible.
5. Health checks for missing or inconsistent files.
6. Documentation in `docs/ServerTypes.md`.
7. A changelog entry.

Avoid hard-coding an installation directory. Detection should start from the folder selected by the user.

## Pull requests

Keep pull requests focused and explain:

- What changed
- Why it changed
- How it was tested
- Which server types are affected
- Whether configuration migration is required

Large UI redesigns and broad refactors should be discussed before implementation.

## Documentation style

- Use clear English.
- Prefer concrete paths and examples.
- Distinguish automatic behavior from required manual configuration.
- Do not claim support that has not been implemented and tested.

## License

By contributing, you agree that your contribution may be distributed under the repository's MIT License.
