"""claude-updater self-check adapter — PyPI version check."""

from __future__ import annotations

import json
import subprocess
from importlib.metadata import PackageNotFoundError, version as _get_pkg_version
from urllib.request import urlopen
from urllib.error import URLError

from claude_updater.adapters.base import ReleaseInfo, ToolAdapter, gh_get_releases


def _normalize_calver(v: str) -> str:
    """Normalize CalVer: '2026.03.2' → '2026.3.2' to match PyPI normalization."""
    return ".".join(str(int(p)) if p.isdigit() else p for p in v.split("."))


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
        # Re-read from metadata to pick up version changes after self-update
        try:
            ver = _get_pkg_version("claude-updater")
        except PackageNotFoundError:
            from claude_updater import __version__ as ver
        return _normalize_calver(ver)

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
        try:
            r = subprocess.run(
                ["uv", "tool", "upgrade", "claude-updater"],
                capture_output=True, text=True, timeout=120,
            )
            return r.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
