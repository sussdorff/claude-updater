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


def _detect_install_method() -> str:
    """Detect how claude-updater was installed: 'uv', 'pipx', or 'pip'."""
    # Check uv first
    try:
        r = subprocess.run(
            ["uv", "tool", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0 and "claude-updater" in r.stdout:
            return "uv"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    # Check pipx
    try:
        r = subprocess.run(
            ["pipx", "list", "--short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0 and "claude-updater" in r.stdout:
            return "pipx"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "pip"


class ClaudeUpdaterAdapter(ToolAdapter):
    @property
    def name(self) -> str:
        return "claude-updater"

    @property
    def key(self) -> str:
        return "claude_updater_self"

    @property
    def update_command(self) -> str:
        method = _detect_install_method()
        if method == "uv":
            return "uv tool upgrade claude-updater"
        if method == "pipx":
            return "pipx upgrade claude-updater"
        return "pip install --upgrade claude-updater"

    def get_installed_version(self) -> str:
        # Ask uv directly for the tool version to avoid editable-install conflicts
        try:
            r = subprocess.run(
                ["uv", "tool", "list"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    if line.startswith("claude-updater "):
                        # Format: "claude-updater v2026.3.6"
                        ver = line.split()[-1].lstrip("v")
                        return _normalize_calver(ver)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        # Check pipx
        try:
            r = subprocess.run(
                ["pipx", "list", "--short"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    if line.startswith("claude-updater "):
                        ver = line.split()[-1].lstrip("v")
                        return _normalize_calver(ver)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        # Fallback to metadata (may hit dev install)
        try:
            ver = _get_pkg_version("claude-updater")
        except PackageNotFoundError:
            from claude_updater import __version__ as ver
        return _normalize_calver(ver)

    def get_latest_version(self) -> str:
        try:
            with urlopen(
                "https://pypi.org/pypi/claude-updater/json", timeout=10
            ) as resp:
                data = json.loads(resp.read())
                return data["info"]["version"]
        except (URLError, json.JSONDecodeError, KeyError, OSError):
            return ""

    def get_changelog_delta(self, from_ver: str, to_ver: str) -> str:
        return ""

    def get_releases(self, limit: int = 5) -> list[ReleaseInfo]:
        return gh_get_releases("sussdorff/claude-updater", limit)

    def apply_update(self) -> bool:
        method = _detect_install_method()

        # Try PyPI upgrade first (works for published releases)
        if method == "uv":
            cmds = [["uv", "tool", "upgrade", "claude-updater"]]
        elif method == "pipx":
            cmds = [["pipx", "upgrade", "claude-updater"]]
        else:
            cmds = [["pip", "install", "--upgrade", "claude-updater"]]

        # For pipx/uv: if PyPI upgrade fails (e.g. installed from local path),
        # try reinstall from PyPI as fallback
        if method == "pipx":
            cmds.append(["pipx", "install", "--force", "claude-updater"])
        elif method == "uv":
            cmds.append(["uv", "tool", "install", "--force", "claude-updater"])

        for cmd in cmds:
            try:
                r = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if r.returncode == 0:
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        return False
