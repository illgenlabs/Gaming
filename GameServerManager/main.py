from __future__ import annotations

import socket
import sys
import threading
from typing import Callable

from ui.gui import GameServerManagerApp


CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 47653
VALID_COMMANDS = {"start-active", "scheduled-maintenance", "show"}


def argument_to_command(arguments: list[str]) -> str:
    if "--scheduled-maintenance" in arguments:
        return "scheduled-maintenance"
    if "--start-active" in arguments:
        return "start-active"
    return "show"


def notify_existing_instance(command: str) -> bool:
    try:
        with socket.create_connection((CONTROL_HOST, CONTROL_PORT), timeout=0.5) as client:
            client.sendall((command + "\n").encode("utf-8"))
        return True
    except OSError:
        return False


def start_control_server(callback: Callable[[str], None]) -> socket.socket:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((CONTROL_HOST, CONTROL_PORT))
    server.listen(5)

    def worker() -> None:
        while True:
            try:
                client, _ = server.accept()
            except OSError:
                return
            with client:
                try:
                    command = client.recv(256).decode("utf-8", errors="replace").strip()
                except OSError:
                    continue
            if command in VALID_COMMANDS:
                callback(command)

    threading.Thread(target=worker, daemon=True).start()
    return server


def main() -> None:
    command = argument_to_command(sys.argv[1:])
    if notify_existing_instance(command):
        return

    app = GameServerManagerApp(initial_command=command)
    control_server = start_control_server(
        lambda received: app.after(0, lambda: app.handle_external_command(received))
    )
    try:
        app.mainloop()
    finally:
        control_server.close()


if __name__ == "__main__":
    main()
