"""beads CLI adapter — cross-platform version check and update.

Uses brew on macOS/Linux, GitHub releases → ~/.local/bin/ on Windows.
"""

from __future__ import annotations

import json
import platform
import subprocess

from claude_updater.adapters.base import (
    ReleaseInfo,
    ToolAdapter,
    download_gh_release_binary,
    gh_changelog_delta,
    gh_get_releases,
)

_IS_WINDOWS = platform.system() == "Windows"


class BeadsCliAdapter(ToolAdapter):
    @property
    def name(self) -> str:
        return "beads CLI"

    @property
    def key(self) -> str:
        return "beads_cli"

    @property
    def update_command(self) -> str:
        if _IS_WINDOWS:
            return "claude-updater update (GitHub release → ~/.local/bin/)"
        return "brew upgrade beads"

    def get_installed_version(self) -> str:
        try:
            r = subprocess.run(
                ["bd", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                # Output: "bd version 0.59.0 (hash)"
                parts = r.stdout.strip().split()
                if len(parts) >= 3:
                    return parts[2]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        if not _IS_WINDOWS:
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
            except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
                pass

        return ""

    def get_latest_version(self) -> str:
        try:
            r = subprocess.run(
                ["gh", "api", "repos/steveyegge/beads/releases/latest",
                 "--jq", ".tag_name"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                return r.stdout.strip().lstrip("v")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        if not _IS_WINDOWS:
            try:
                r = subprocess.run(
                    ["brew", "info", "--json=v2", "beads"],
                    capture_output=True, text=True, timeout=15,
                )
                if r.returncode == 0:
                    data = json.loads(r.stdout)
                    return data["formulae"][0]["versions"]["stable"]
            except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
                pass

        return ""

    def get_releases(self, limit: int = 5) -> list[ReleaseInfo]:
        return gh_get_releases("steveyegge/beads", limit)

    def get_changelog_delta(self, from_ver: str, to_ver: str) -> str:
        return gh_changelog_delta("steveyegge/beads", from_ver, to_ver)

    def apply_update(self) -> bool:
        if _IS_WINDOWS:
            latest = self.get_latest_version()
            if not latest:
                return False
            return download_gh_release_binary(
                repo="steveyegge/beads",
                asset_name=f"beads_{latest}_windows_amd64.zip",
                binary_name="bd.exe",
            )
        try:
            r = subprocess.run(
                ["brew", "upgrade", "beads"],
                capture_output=True, text=True, timeout=120,
            )
            return r.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
