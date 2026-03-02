"""claude-mem plugin adapter — git-based update check."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from claude_updater.adapters.base import ToolAdapter, VersionInfo


class ClaudeMemAdapter(ToolAdapter):
    _default_plugin_dir = "~/.claude/plugins/marketplaces/thedotmack"

    @property
    def name(self) -> str:
        return "claude-mem"

    @property
    def key(self) -> str:
        return "claude_mem"

    @property
    def update_command(self) -> str:
        return "git pull"

    @property
    def _plugin_dir(self) -> Path:
        d = self._settings.get("plugin_dir", self._default_plugin_dir)
        return Path(d).expanduser()

    def get_installed_version(self) -> str:
        pkg_json = self._plugin_dir / "package.json"
        try:
            with open(pkg_json) as f:
                return json.load(f).get("version", "")
        except (FileNotFoundError, json.JSONDecodeError):
            return ""

    def get_latest_version(self) -> str:
        # For git plugins, we check if there are remote changes
        # The "latest" is whatever is on origin after fetch
        if self._has_remote_changes():
            return "update-available"
        return self.get_installed_version()

    def _has_remote_changes(self) -> bool:
        try:
            r = subprocess.run(
                ["git", "-C", str(self._plugin_dir), "fetch", "--dry-run"],
                capture_output=True, text=True, timeout=15,
            )
            return bool(r.stderr.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def has_update(self) -> bool:
        return self._has_remote_changes()

    def get_changelog_delta(self, from_ver: str, to_ver: str) -> str:
        changelog = self._plugin_dir / "CHANGELOG.md"
        if not changelog.exists():
            return ""
        try:
            text = changelog.read_text()
            lines = text.splitlines()
            result = []
            found_start = False
            for line in lines:
                if line.startswith("## [") or line.startswith("## v"):
                    if found_start:
                        break
                    if from_ver in line:
                        found_start = True
                        continue
                    if not found_start:
                        result.append(line)
                elif not found_start:
                    result.append(line)
            return "\n".join(result)
        except OSError:
            return ""

    def apply_update(self) -> bool:
        try:
            r = subprocess.run(
                ["git", "-C", str(self._plugin_dir), "pull", "--ff-only", "origin", "main"],
                capture_output=True, text=True, timeout=30,
            )
            return r.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def check_status(self) -> VersionInfo:
        installed = self.get_installed_version()
        update = self.has_update()
        return VersionInfo(
            tool_name=self.name,
            key=self.key,
            installed_version=installed,
            latest_version="update-available" if update else installed,
            has_update=update,
            update_method=self.update_command if update else "",
        )
