from __future__ import annotations

import locale
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, TextIO

from core.paths import LOG_DIR, ensure_runtime_directories
from core.server_types import get_console_stop_command, supports_console_stop, supports_managed_pid_stop
from models import ServerInfo


class ProcessManager:
    def __init__(
        self,
        output_callback: Callable[[str, str], None] | None = None,
        exit_callback: Callable[[str, int], None] | None = None,
    ) -> None:
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.logs: dict[str, TextIO] = {}
        self.lock = threading.RLock()
        self.output_callback = output_callback
        self.exit_callback = exit_callback
        # Server IDs for which a deliberate stop is currently in progress.
        # Windows reports Ctrl+C/Ctrl+Break termination as 0xC000013A
        # (decimal 3221225786), although this is the expected Windrose exit.
        self.requested_stops: set[str] = set()

    def is_running(self, server_id: str) -> bool:
        with self.lock:
            process = self.processes.get(server_id)
            return bool(process and process.poll() is None)

    def start(self, server: ServerInfo) -> int:
        if self.is_running(server.id):
            raise RuntimeError("The server is already running.")

        script = server.action_scripts.get("start", "").strip()

        if not script:
            raise RuntimeError("No start script is configured.")

        if server.server_type == "windrose":
            process = self._popen_windrose(server)
        else:
            process = self._popen_script(
                server=server,
                script=script,
                interactive=True,
            )

        # Common startup errors such as an invalid Java path, a missing JAR,
        # or a failing batch file usually terminate immediately. This brief
        # probe lets the application surface the actual console output.
        time.sleep(0.8)

        if process.poll() is not None:
            output, _ = process.communicate()
            details = (output or "").strip()

            message = (
                "The start script exited immediately "
                f"(Code {process.returncode})."
            )

            if details:
                message += f"\n\nOutput:\n{details[-4000:]}"
            else:
                message += (
                    "\n\nThe script produced no output. "
                    "Check the Java path, JAR file, and script contents."
                )

            raise RuntimeError(message)

        ensure_runtime_directories()
        log_dir = LOG_DIR

        log_file = (log_dir / f"{server.id}.log").open(
            "a",
            encoding="utf-8",
            errors="replace",
        )

        log_file.write(
            f"\n===== Start {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n"
        )
        log_file.flush()

        with self.lock:
            self.processes[server.id] = process
            self.logs[server.id] = log_file

        reader_thread = threading.Thread(
            target=self._read,
            args=(server.id, process, log_file),
            daemon=True,
        )
        reader_thread.start()

        self._emit(
            server.id,
            f"Process started (PID {process.pid}).",
        )

        return process.pid

    def stop(
        self,
        server: ServerInfo,
        timeout: int = 40,
    ) -> bool:
        if not self.is_running(server.id):
            return True

        self.requested_stops.add(server.id)

        if supports_managed_pid_stop(server.server_type):
            stopped = self._stop_managed_process(server, timeout)
            if not stopped and self.is_running(server.id):
                self.requested_stops.discard(server.id)
            return stopped

        stop_script = server.action_scripts.get("stop", "").strip()

        if stop_script:
            code, output = self.run_action_script(
                server=server,
                action="stop",
                timeout=timeout,
            )

            if output:
                self._emit(server.id, output)

            if code != 0:
                return False

        elif supports_console_stop(server.server_type):
            process = self.processes[server.id]

            if process.stdin is None:
                return False

            try:
                command = get_console_stop_command(server.server_type)
                process.stdin.write(command + "\n")
                process.stdin.flush()
                self._emit(server.id, f"Console command '{command}' sent.")
            except (BrokenPipeError, OSError):
                return False

        else:
            raise RuntimeError(
                "No stop script is configured for this server."
            )

        process = self.processes[server.id]
        try:
            process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            self._emit(
                server.id,
                "The server did not stop within the timeout; requesting process termination.",
            )

        try:
            process.terminate()
            process.wait(timeout=10)
            return True
        except subprocess.TimeoutExpired:
            self._emit(
                server.id,
                "The process did not terminate; a forced stop is required.",
            )
            return False

    def _stop_managed_process(self, server: ServerInfo, timeout: int) -> bool:
        """Stop the exact process tree started and tracked by the manager."""
        process = self.processes[server.id]

        if process.poll() is not None:
            return True

        if os.name == "nt":
            self._emit(
                server.id,
                f"Stopping managed process tree for PID {process.pid}...",
            )

            result = subprocess.run(
                [
                    "taskkill",
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                ],
                capture_output=True,
                text=True,
                encoding=locale.getpreferredencoding(False) or "utf-8",
                errors="replace",
                check=False,
            )

            # taskkill can return a non-zero code if the process exits between
            # the poll above and the command. The Popen handle is authoritative.
            if result.returncode != 0 and process.poll() is None:
                detail = (result.stderr or result.stdout or "").strip()
                if detail:
                    self._emit(server.id, f"taskkill reported: {detail}")
        else:
            try:
                process.kill()
            except OSError as exc:
                if process.poll() is None:
                    self._emit(server.id, f"Process termination failed: {exc}")
                    return False

        try:
            process.wait(timeout=max(1, min(timeout, 15)))
            self._emit(server.id, "Managed process tree stopped successfully.")
            return True
        except subprocess.TimeoutExpired:
            self._emit(
                server.id,
                f"PID {process.pid} is still running after taskkill.",
            )
            return False

    def restart(self, server: ServerInfo) -> None:
        """Restarts by stopping the managed process and starting it again."""
        stop_script = server.action_scripts.get("stop", "").strip()

        if (
            not supports_managed_pid_stop(server.server_type)
            and not supports_console_stop(server.server_type)
            and not stop_script
        ):
            raise RuntimeError("No stop script is configured.")

        if self.is_running(server.id):
            stopped = self.stop(server)
            if not stopped:
                raise RuntimeError("The server did not respond to the stop request.")

        time.sleep(1)
        self.start(server)

    def update(
        self,
        server: ServerInfo,
    ) -> tuple[int, str]:
        if self.is_running(server.id):
            raise RuntimeError(
                "The server must be stopped before updating."
            )

        return self.run_action_script(
            server=server,
            action="update",
            timeout=1800,
        )

    def run_action_script(
        self,
        server: ServerInfo,
        action: str,
        timeout: int = 900,
    ) -> tuple[int, str]:
        script = server.action_scripts.get(action, "").strip()

        if not script:
            raise RuntimeError(
                f"No {action} script is configured."
            )

        process = self._popen_script(
            server=server,
            script=script,
            interactive=False,
        )

        try:
            output, _ = process.communicate(timeout=timeout)

        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()

            raise RuntimeError(
                f"The {action} script exceeded the time limit."
                f"\n\n{output or ''}"
            )

        return (
            process.returncode or 0,
            (output or "").strip(),
        )

    def send_command(self, server_id: str, command: str) -> None:
        """Send a command to a running process with an attached console."""
        cleaned = command.strip()
        if not cleaned:
            raise ValueError("The command cannot be empty.")

        with self.lock:
            process = self.processes.get(server_id)

        if process is None or process.poll() is not None:
            raise RuntimeError("The server is not running.")
        if process.stdin is None:
            raise RuntimeError("No interactive console is available for this server.")

        try:
            process.stdin.write(cleaned + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise RuntimeError("The command could not be sent to the server console.") from exc

    def get_process_id(self, server_id: str) -> int | None:
        with self.lock:
            process = self.processes.get(server_id)
            if process is None or process.poll() is not None:
                return None
            return process.pid

    def force_stop(self, server_id: str) -> None:
        process = self.processes.get(server_id)

        if process is None or process.poll() is not None:
            return

        if os.name == "nt":
            subprocess.run(
                [
                    "taskkill",
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                ],
                capture_output=True,
                check=False,
            )
        else:
            process.kill()


    def _popen_windrose(self, server: ServerInfo) -> subprocess.Popen[str]:
        """Start Windrose directly without its separate Unreal ``-log`` window."""
        server_root = Path(server.path).resolve()
        candidates = [
            server_root / "R5" / "Binaries" / "Win64" / "WindroseServer-Win64-Shipping.exe",
            server_root / "WindroseServer-Win64-Shipping.exe",
        ]
        executable = next((path for path in candidates if path.is_file()), None)
        if executable is None:
            matches = list(server_root.rglob("WindroseServer-Win64-Shipping.exe"))
            executable = matches[0] if matches else None
        if executable is None:
            raise RuntimeError(
                "Windrose server executable was not found below:\n" + str(server_root)
            )

        creation_flags = 0
        startup_info = None
        if os.name == "nt":
            # -log creates Unreal's separate visible console window. Redirect
            # output to stdout instead. CREATE_NEW_CONSOLE plus SW_HIDE keeps the
            # child console invisible while the output remains available in the
            # application's integrated Console tab.
            creation_flags = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NEW_CONSOLE
            )
            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup_info.wShowWindow = subprocess.SW_HIDE

        encoding = locale.getpreferredencoding(False) or "utf-8"
        return subprocess.Popen(
            [
                str(executable),
                "-stdout",
                "-FullStdOutLogOutput",
                "-unattended",
            ],
            cwd=str(server_root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=encoding,
            errors="replace",
            bufsize=1,
            creationflags=creation_flags,
            startupinfo=startup_info,
        )

    def _popen_script(
        self,
        server: ServerInfo,
        script: str,
        interactive: bool,
    ) -> subprocess.Popen[str]:
        server_root = Path(server.path).resolve()

        script_path = Path(script)

        if script_path.is_absolute():
            full_path = script_path.resolve()
        else:
            full_path = (server_root / script_path).resolve()

        try:
            full_path.relative_to(server_root)

        except ValueError as exc:
            raise RuntimeError(
                "The action script is outside the server folder."
            ) from exc

        if not full_path.is_file():
            raise RuntimeError(
                f"Script not found:\n{full_path}"
            )

        suffix = full_path.suffix.lower()

        if suffix in {".bat", ".cmd"}:
            command = [
                "cmd.exe",
                "/d",
                "/c",
                str(full_path),
            ]

        elif suffix == ".ps1":
            command = [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(full_path),
            ]

        elif suffix == ".exe":
            command = [str(full_path)]

        else:
            raise RuntimeError(
                f"Unsupported script type: {full_path.suffix}"
            )

        creation_flags = 0
        startup_info = None

        if os.name == "nt":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
            # Keep script consoles managed by the application instead of
            # opening a separate visible command window.
            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup_info.wShowWindow = subprocess.SW_HIDE

        encoding = locale.getpreferredencoding(False) or "utf-8"

        try:
            return subprocess.Popen(
                command,
                cwd=str(server_root),
                stdin=(
                    subprocess.PIPE
                    if interactive
                    else subprocess.DEVNULL
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding=encoding,
                errors="replace",
                bufsize=1,
                creationflags=creation_flags,
                startupinfo=startup_info,
            )

        except FileNotFoundError as exc:
            raise RuntimeError(
                "The required executable was not found:"
                f"\n{command[0]}"
            ) from exc

        except OSError as exc:
            raise RuntimeError(
                "The script could not be started:"
                f"\n{full_path}\n\n{exc}"
            ) from exc

    def _read(
        self,
        server_id: str,
        process: subprocess.Popen[str],
        log_file: TextIO,
    ) -> None:
        return_code = -1

        try:
            if process.stdout is not None:
                for line in process.stdout:
                    log_file.write(line)
                    log_file.flush()

                    self._emit(
                        server_id,
                        line.rstrip("\r\n"),
                    )

            return_code = process.wait()

        finally:
            try:
                log_file.close()
            except OSError:
                pass

            with self.lock:
                self.processes.pop(server_id, None)
                self.logs.pop(server_id, None)

        requested_stop = server_id in self.requested_stops
        self.requested_stops.discard(server_id)

        callback_code = return_code
        if requested_stop:
            # A deliberate taskkill commonly produces a non-zero Windows exit
            # status. Since the manager requested and confirmed the stop, this
            # is an expected lifecycle event rather than a server crash.
            callback_code = 0
            self._emit(
                server_id,
                "Process stopped after the requested shutdown.",
            )
        else:
            self._emit(
                server_id,
                f"Process exited (Code {return_code}).",
            )

        if self.exit_callback is not None:
            self.exit_callback(
                server_id,
                callback_code,
            )

    def _emit(
        self,
        server_id: str,
        text: str,
    ) -> None:
        if self.output_callback is not None and text:
            self.output_callback(
                server_id,
                text,
            )