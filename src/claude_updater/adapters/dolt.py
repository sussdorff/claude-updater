"""dolt adapter — brew-based version check and update."""

from __future__ import annotations

import json
import subprocess

from claude_updater.adapters.base import ToolAdapter


class DoltAdapter(ToolAdapter):
    @property
    def name(self) -> str:
        return "dolt"

    @property
    def key(self) -> str:
        return "dolt"

    @property
    def update_command(self) -> str:
        return "brew upgrade dolt"

    def get_installed_version(self) -> str:
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
            return ""
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
            return ""

    def get_latest_version(self) -> str:
        try:
            r = subprocess.run(
                ["brew", "info", "--json=v2", "dolt"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                data = json.loads(r.stdout)
                return data["formulae"][0]["versions"]["stable"]
            return ""
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
            return ""

    def get_changelog_delta(self, from_ver: str, to_ver: str) -> str:
        try:
            r = subprocess.run(
                [
                    "gh", "release", "list",
                    "--repo", "dolthub/dolt",
                    "--json", "tagName,body",
                    "--limit", "10",
                ],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                return ""

            releases = json.loads(r.stdout)
            parts = []
            in_range = False
            for rel in releases:
                tag = rel["tagName"]
                ver = tag.lstrip("v")
                if ver == to_ver:
                    in_range = True
                if in_range:
                    body = rel.get("body", "")[:500]
                    parts.append(f"## {tag}\n{body}\n")
                if ver == from_ver:
                    break
            return "\n".join(parts)
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            return ""

    def apply_update(self) -> bool:
        try:
            r = subprocess.run(
                ["brew", "upgrade", "dolt"],
                capture_output=True, text=True, timeout=120,
            )
            return r.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
