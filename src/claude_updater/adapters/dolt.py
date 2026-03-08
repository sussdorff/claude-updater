"""dolt adapter — cross-platform version check and update.

Uses brew on macOS/Linux, GitHub releases on Windows.
"""

from __future__ import annotations

import json
import platform
import re
import subprocess

from claude_updater.adapters.base import ReleaseInfo, ToolAdapter, gh_changelog_delta, gh_get_releases

_IS_WINDOWS = platform.system() == "Windows"


class DoltAdapter(ToolAdapter):
    @property
    def name(self) -> str:
        return "dolt"

    @property
    def key(self) -> str:
        return "dolt"

    @property
    def update_command(self) -> str:
        if _IS_WINDOWS:
            return "winget upgrade dolthub.dolt"
        return "brew upgrade dolt"

    def get_installed_version(self) -> str:
        # Try dolt version directly (works on all platforms)
        try:
            r = subprocess.run(
                ["dolt", "version"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                # Output: "dolt version 1.35.0"
                m = re.search(r"(\d+\.\d+\.\d+)", r.stdout)
                if m:
                    return m.group(1)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback: brew on non-Windows
        if not _IS_WINDOWS:
            try:
                r = subprocess.run(
                    ["brew", "info", "--json=v2", "dolt"],
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
        # Use GitHub API (works on all platforms)
        try:
            r = subprocess.run(
                ["gh", "api", "repos/dolthub/dolt/releases/latest",
                 "--jq", ".tag_name"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                return r.stdout.strip().lstrip("v")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback: brew on non-Windows
        if not _IS_WINDOWS:
            try:
                r = subprocess.run(
                    ["brew", "info", "--json=v2", "dolt"],
                    capture_output=True, text=True, timeout=15,
                )
                if r.returncode == 0:
                    data = json.loads(r.stdout)
                    return data["formulae"][0]["versions"]["stable"]
            except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
                pass

        return ""

    def get_releases(self, limit: int = 5) -> list[ReleaseInfo]:
        return gh_get_releases("dolthub/dolt", limit)

    def get_changelog_delta(self, from_ver: str, to_ver: str) -> str:
        return gh_changelog_delta("dolthub/dolt", from_ver, to_ver)

    def apply_update(self) -> bool:
        if _IS_WINDOWS:
            # Try winget first
            try:
                r = subprocess.run(
                    ["winget", "upgrade", "dolthub.dolt"],
                    capture_output=True, text=True, timeout=120,
                )
                if r.returncode == 0:
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            # Fallback: download from GitHub releases via PowerShell
            try:
                ps_cmd = (
                    "$r = gh api repos/dolthub/dolt/releases/latest --jq '.assets[] | select(.name | endswith(\"windows-amd64.zip\")) | .browser_download_url';"
                    "if ($r) { $tmp = \"$env:TEMP\\dolt.zip\"; Invoke-WebRequest $r -OutFile $tmp;"
                    "Expand-Archive $tmp -DestinationPath \"$env:LOCALAPPDATA\\dolt\" -Force; Remove-Item $tmp }"
                )
                r = subprocess.run(
                    ["powershell", "-Command", ps_cmd],
                    capture_output=True, text=True, timeout=120,
                )
                return r.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return False
        else:
            try:
                r = subprocess.run(
                    ["brew", "upgrade", "dolt"],
                    capture_output=True, text=True, timeout=120,
                )
                return r.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return False
