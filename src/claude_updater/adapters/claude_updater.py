"""claude-updater self-check adapter — PyPI version check."""

from __future__ import annotations

import json
from urllib.request import urlopen
from urllib.error import URLError

from claude_updater import __version__
from claude_updater.adapters.base import ReleaseInfo, ToolAdapter, gh_get_releases


class ClaudeUpdaterAdapter(ToolAdapter):
    @property
    def name(self) -> str:
        return "claude-updater"

    @property
    def key(self) -> str:
        return "claude_updater_self"

    @property
    def update_command(self) -> str:
        return "uv tool upgrade claude-updater"

    def get_installed_version(self) -> str:
        return __version__

    def get_latest_version(self) -> str:
        try:
            with urlopen("https://pypi.org/pypi/claude-updater/json", timeout=10) as resp:
                data = json.loads(resp.read())
                return data["info"]["version"]
        except (URLError, json.JSONDecodeError, KeyError, OSError):
            return ""

    def get_changelog_delta(self, from_ver: str, to_ver: str) -> str:
        return ""

    def get_releases(self, limit: int = 5) -> list[ReleaseInfo]:
        return gh_get_releases("sussdorff/claude-updater", limit)

    def apply_update(self) -> bool:
        # Don't self-update — just inform
        return False
