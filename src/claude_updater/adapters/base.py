from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class VersionInfo:
    tool_name: str
    key: str
    installed_version: str
    latest_version: str
    has_update: bool
    update_method: str
    changelog_delta: str = ""


class ToolAdapter(ABC):
    def __init__(self) -> None:
        self._settings: dict = {}

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def key(self) -> str: ...

    @abstractmethod
    def get_installed_version(self) -> str: ...

    @abstractmethod
    def get_latest_version(self) -> str: ...

    @abstractmethod
    def get_changelog_delta(self, from_ver: str, to_ver: str) -> str: ...

    @abstractmethod
    def apply_update(self) -> bool: ...

    @property
    def update_command(self) -> str:
        """Human-readable update method description."""
        return ""

    def has_update(self) -> bool:
        return self.get_installed_version() != self.get_latest_version()

    def check_status(self) -> VersionInfo:
        installed = self.get_installed_version()
        latest = self.get_latest_version()
        update = installed != latest and bool(installed) and bool(latest)
        return VersionInfo(
            tool_name=self.name,
            key=self.key,
            installed_version=installed,
            latest_version=latest,
            has_update=update,
            update_method=self.update_command if update else "",
            changelog_delta="",
        )

    def configure(self, settings: dict) -> None:
        self._settings = settings
