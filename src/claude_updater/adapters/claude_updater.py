"""claude-updater self-check adapter — PyPI version check."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version as _get_pkg_version
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from claude_updater.adapters.base import ReleaseInfo, ToolAdapter, gh_get_releases


def _normalize_calver(v: str) -> str:
    """Normalize CalVer: '2026.03.2' → '2026.3.2' to match PyPI normalization."""
    return ".".join(str(int(p)) if p.isdigit() else p for p in v.split("."))


def _is_local_install() -> bool:
    """Check if claude-updater was installed from a local path (not PyPI).

    Local installs have a direct_url.json in the dist-info with a file:// URL,
    or report version 0.0.0 (dev stub from pyproject.toml).
    """
    try:
        ver = _get_pkg_version("claude-updater")
        if ver.startswith("0.0.0"):
            return True
    except PackageNotFoundError:
        pass

    # Check direct_url.json (PEP 610) — present for local/VCS installs
    for p in sys.path:
        dist_info = Path(p).glob("claude_updater-*.dist-info/direct_url.json")
        for url_file in dist_info:
            try:
                data = json.loads(url_file.read_text())
                if data.get("url", "").startswith("file://"):
                    return True
            except (json.JSONDecodeError, OSError):
                pass
    return False


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
        if _is_local_install():
            return "git pull + reinstall (managed locally)"
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

    def check_status(self):
        """Override to suppress update notification for local installs."""
        info = super().check_status()
        if _is_local_install() and info.has_update:
            # Local install — version mismatch with PyPI is expected.
            # Don't flag as update, it's managed via git pull.
            info.has_update = False
            info.update_method = "git pull + reinstall (managed locally)"
        return info

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
        if _is_local_install():
            # Managed via git — self-update not applicable
            return True

        method = _detect_install_method()
        if method == "uv":
            cmd = ["uv", "tool", "upgrade", "claude-updater"]
        elif method == "pipx":
            cmd = ["pipx", "upgrade", "claude-updater"]
        else:
            cmd = ["pip", "install", "--upgrade", "claude-updater"]
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return r.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
