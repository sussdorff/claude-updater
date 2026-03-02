"""beads plugin adapter — git-based update check."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from claude_updater.adapters.base import ToolAdapter


class BeadsPluginAdapter(ToolAdapter):
    _default_plugin_dir = "~/.claude/plugins/marketplaces/beads-marketplace"

    @property
    def name(self) -> str:
        return "beads plugin"

    @property
    def key(self) -> str:
        return "beads_plugin"

    @property
    def update_command(self) -> str:
        return "git pull"

    @property
    def _plugin_dir(self) -> Path:
        d = self._settings.get("plugin_dir", self._default_plugin_dir)
        return Path(d).expanduser()

    @property
    def _plugin_json(self) -> Path:
        return self._plugin_dir / "claude-plugin" / ".claude-plugin" / "plugin.json"

    def get_installed_version(self) -> str:
        try:
            with open(self._plugin_json) as f:
                return json.load(f).get("version", "")
        except (FileNotFoundError, json.JSONDecodeError):
            return ""

    def get_latest_version(self) -> str:
        plugin_dir = str(self._plugin_dir)
        # Fetch remote to update tracking refs
        try:
            subprocess.run(
                ["git", "-C", plugin_dir, "fetch", "origin"],
                capture_output=True, text=True, timeout=15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return self.get_installed_version()

        # Read version from remote's plugin.json
        try:
            r = subprocess.run(
                ["git", "-C", plugin_dir, "show",
                 "origin/main:claude-plugin/.claude-plugin/plugin.json"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                return json.loads(r.stdout).get("version", "")
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pass
        return self.get_installed_version()

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
                if line.startswith("## [") or line.startswith("## "):
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

