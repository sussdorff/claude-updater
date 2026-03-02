"""Claude Code adapter — checks via gh API and claude --version."""

from __future__ import annotations

import json
import subprocess

from claude_updater.adapters.base import ToolAdapter, VersionInfo


class ClaudeCodeAdapter(ToolAdapter):
    @property
    def name(self) -> str:
        return "Claude Code"

    @property
    def key(self) -> str:
        return "claude_code"

    @property
    def update_command(self) -> str:
        return "auto-update (restart Claude Code)"

    def get_installed_version(self) -> str:
        try:
            r = subprocess.run(
                ["claude", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            # Output is like "2.1.63 (Claude Code)"
            return r.stdout.strip().split()[0] if r.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def get_latest_version(self) -> str:
        try:
            r = subprocess.run(
                ["gh", "api", "repos/anthropics/claude-code/releases/latest", "--jq", ".tag_name"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                return r.stdout.strip().lstrip("v")
            return ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def get_changelog_delta(self, from_ver: str, to_ver: str) -> str:
        try:
            r = subprocess.run(
                [
                    "gh", "api", "repos/anthropics/claude-code/releases",
                    "--paginate", "--jq", ".[].tag_name",
                ],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                return ""

            tags = r.stdout.strip().splitlines()[:20]
            in_range = False
            changelog_parts = []

            for tag in tags:
                ver = tag.lstrip("v")
                if ver == to_ver:
                    in_range = True
                if in_range:
                    body_r = subprocess.run(
                        [
                            "gh", "api",
                            f"repos/anthropics/claude-code/releases/tags/{tag}",
                            "--jq", ".body",
                        ],
                        capture_output=True, text=True, timeout=15,
                    )
                    if body_r.returncode == 0:
                        changelog_parts.append(f"## {tag}\n{body_r.stdout.strip()}\n")
                if ver == from_ver:
                    break

            return "\n".join(changelog_parts)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def apply_update(self) -> bool:
        # Claude Code has auto-update; we just inform the user
        return False

