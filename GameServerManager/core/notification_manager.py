from __future__ import annotations

import socket
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NtfySettings:
    enabled: bool = False
    server_url: str = "https://ntfy.sh"
    topic: str = ""


class NotificationManager:
    """Send concise notifications through an ntfy topic without credentials."""

    def __init__(self, settings: NtfySettings) -> None:
        self.settings = settings

    def send_test(self) -> None:
        self._send(
            title="Game Server Manager test",
            body=(
                "This is a test notification from Game Server Manager.\n\n"
                "The configured ntfy topic is working."
            ),
        )

    def send_error(self, title: str, details: str) -> None:
        if not self.settings.enabled:
            return
        body = (
            "Game Server Manager detected an error.\n\n"
            f"Time: {datetime.now().astimezone().isoformat(timespec='seconds')}\n"
            f"Computer: {socket.gethostname()}\n"
            f"Python: {sys.version.split()[0]}\n\n"
            f"{title}\n\n{details}"
        )
        self._send(title=f"Game Server Manager error: {title}", body=body)

    def send_exception(self, title: str, exc_type, exc_value, exc_traceback) -> None:
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        self.send_error(title, details)

    def _send(self, title: str, body: str) -> None:
        cfg = self.settings
        server_url = cfg.server_url.strip().rstrip("/")
        topic = cfg.topic.strip()
        if not server_url:
            raise ValueError("An ntfy server URL is required.")
        parsed = urllib.parse.urlparse(server_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("The ntfy server URL must begin with http:// or https://.")
        if not topic:
            raise ValueError("An ntfy topic is required.")
        if any(char in topic for char in "/?#"):
            raise ValueError("The ntfy topic must not contain /, ?, or #.")

        url = f"{server_url}/{urllib.parse.quote(topic, safe='-_')}"
        request = urllib.request.Request(
            url,
            data=body.encode("utf-8"),
            method="POST",
            headers={
                "Title": title.encode("ascii", "ignore").decode("ascii") or "Game Server Manager",
                "Priority": "high",
                "Tags": "warning,computer",
                "User-Agent": "GameServerManager/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"ntfy returned HTTP status {response.status}.")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"ntfy returned HTTP status {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"The ntfy server could not be reached: {exc.reason}") from exc
