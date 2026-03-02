"""beads CLI adapter — brew-based version check and update."""

from __future__ import annotations

import json
import subprocess

from claude_updater.adapters.base import ReleaseInfo, ToolAdapter, gh_changelog_delta, gh_get_releases


class BeadsCliAdapter(ToolAdapter):
    @property
    def name(self) -> str:
        return "beads CLI"

    @property
    def key(self) -> str:
        return "beads_cli"

    @property
    def update_command(self) -> str:
        return "brew upgrade beads"

    def get_installed_version(self) -> str:
        try:
            r = subprocess.run(
                ["brew", "info", "--json=v2", "beads"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                data = json.loads(r.stdout)
                linked = data["formulae"][0].get("linked_keg")
                if linked:
                    return linked
            return ""
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
            return ""

    def get_latest_version(self) -> str:
        try:
            r = subprocess.run(
                ["brew", "info", "--json=v2", "beads"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                data = json.loads(r.stdout)
                return data["formulae"][0]["versions"]["stable"]
            return ""
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
            return ""

    def get_releases(self, limit: int = 5) -> list[ReleaseInfo]:
        return gh_get_releases("steveyegge/beads", limit)

    def get_changelog_delta(self, from_ver: str, to_ver: str) -> str:
        return gh_changelog_delta("steveyegge/beads", from_ver, to_ver)

    def apply_update(self) -> bool:
        try:
            r = subprocess.run(
                ["brew", "upgrade", "beads"],
                capture_output=True, text=True, timeout=120,
            )
            return r.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
