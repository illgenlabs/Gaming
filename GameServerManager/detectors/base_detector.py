from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from models import ServerInfo


class BaseDetector(ABC):
    @abstractmethod
    def can_handle(self, path: Path) -> bool:
        raise NotImplementedError

    @abstractmethod
    def detect(self, path: Path) -> ServerInfo:
        raise NotImplementedError
