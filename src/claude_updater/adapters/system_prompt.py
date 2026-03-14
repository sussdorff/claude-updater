"""System Prompt adapter — tracks Claude Code system prompt changes via cchistory.

Detects when Anthropic changes the system prompt between CC versions.
Also reports whether a custom system prompt or output style is active.

Data source: https://cchistory.mariozechner.at/data/
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

from claude_updater.adapters.base import ReleaseInfo, ToolAdapter, VersionInfo

CCHISTORY_BASE = "https://cchistory.mariozechner.at/data"
CCHISTORY_VERSIONS_URL = f"{CCHISTORY_BASE}/versions.json"

# Sections we care about for behavioral diff
TRACKED_SECTIONS = [
    "Output efficiency",
    "Doing tasks",
    "Tone and style",
    "Executing actions with care",
    "Using your tools",
    "System",
]


def _fetch_json(url: str, timeout: int = 15) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "claude-updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _fetch_text(url: str, timeout: int = 15) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "claude-updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except Exception:
        return ""


def _get_cc_version() -> str:
    """Get currently installed Claude Code version."""
    try:
        r = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout.strip().split()[0] if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _get_available_versions() -> list[str]:
    """Fetch all available prompt versions from cchistory."""
    data = _fetch_json(CCHISTORY_VERSIONS_URL)
    if not isinstance(data, dict) or "versions" not in data:
        return []
    return [v["version"] for v in data["versions"]]


def _find_prompt_version(cc_version: str, available: list[str]) -> str:
    """Find the matching prompt version for a CC version.

    cchistory tracks prompts per CC version. If exact match isn't available,
    find the closest lower version.
    """
    if cc_version in available:
        return cc_version
    # Find closest version <= cc_version
    try:

        def ver_tuple(v: str) -> tuple:
            return tuple(int(x) for x in v.split(".") if x.isdigit())

        cc_t = ver_tuple(cc_version)
        candidates = [v for v in available if ver_tuple(v) <= cc_t]
        if candidates:
            candidates.sort(key=lambda v: ver_tuple(v))
            return candidates[-1]
    except (ValueError, TypeError):
        pass
    # Fallback: latest available
    return available[-1] if available else ""


def _fetch_prompt(version: str) -> str:
    """Fetch the full system prompt text for a version."""
    url = f"{CCHISTORY_BASE}/prompts-{version}.md"
    return _fetch_text(url)


def _extract_sections(prompt_text: str) -> dict[str, str]:
    """Extract named sections from a system prompt."""
    sections: dict[str, str] = {}
    current_name = ""
    current_lines: list[str] = []

    for line in prompt_text.splitlines():
        # Match ## or # section headers
        m = re.match(r"^#{1,3}\s+(.+)", line)
        if m:
            if current_name:
                sections[current_name] = "\n".join(current_lines).strip()
            current_name = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_name:
        sections[current_name] = "\n".join(current_lines).strip()

    return sections


def _prompt_hash(text: str) -> str:
    """Short hash of prompt text for quick comparison."""
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _diff_sections(old_text: str, new_text: str) -> str:
    """Compare two prompts section-by-section. Returns human-readable diff summary."""
    old_sections = _extract_sections(old_text)
    new_sections = _extract_sections(new_text)

    all_keys = list(
        dict.fromkeys(list(old_sections.keys()) + list(new_sections.keys()))
    )

    changes: list[str] = []
    for key in all_keys:
        old = old_sections.get(key, "")
        new = new_sections.get(key, "")
        if old == new:
            continue

        if not old:
            lines = len(new.splitlines())
            changes.append(f"  + NEW: {key} ({lines} lines)")
        elif not new:
            changes.append(f"  - REMOVED: {key}")
        else:
            old_lines = len(old.splitlines())
            new_lines = len(new.splitlines())
            delta = new_lines - old_lines
            sign = "+" if delta > 0 else ""
            # Check if it's a tracked behavioral section
            is_behavioral = any(t.lower() in key.lower() for t in TRACKED_SECTIONS)
            marker = " [BEHAVIORAL]" if is_behavioral else ""
            changes.append(
                f"  ~ CHANGED: {key} ({old_lines} -> {new_lines} lines, {sign}{delta}){marker}"
            )

    if not changes:
        return "  No section-level changes detected (formatting only)"

    return "\n".join(changes)


def _detect_custom_prompt() -> str | None:
    """Detect if a custom system prompt or output style is configured.

    Checks:
    - ~/.claude/output-style.md (output style override)
    - ~/.claude/settings.json for outputStyle setting
    """
    home = Path.home()
    indicators: list[str] = []

    # Check output style file
    output_style = home / ".claude" / "output-style.md"
    if output_style.exists():
        indicators.append(f"output-style: {output_style}")

    # Check settings for outputStyle
    for settings_path in [
        home / ".claude" / "settings.json",
        home / ".claude" / "settings.local.json",
    ]:
        if settings_path.exists():
            try:
                data = json.loads(settings_path.read_text())
                if "outputStyle" in data:
                    indicators.append(
                        f"outputStyle in {settings_path.name}: {data['outputStyle']}"
                    )
            except (json.JSONDecodeError, OSError):
                pass

    return ", ".join(indicators) if indicators else None


class _PromptCache:
    """Cache for the last-reviewed prompt version."""

    @property
    def path(self) -> Path:
        xdg = os.environ.get("XDG_CACHE_HOME")
        base = Path(xdg) if xdg else Path.home() / ".cache"
        return base / "claude-updater" / "system-prompt-state.json"

    def read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def write(self, version: str, prompt_hash: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "reviewed_version": version,
                    "prompt_hash": prompt_hash,
                },
                indent=2,
            )
        )

    def mark_reviewed(self, version: str, prompt_hash: str) -> None:
        self.write(version, prompt_hash)


class SystemPromptAdapter(ToolAdapter):
    @property
    def name(self) -> str:
        return "System Prompt"

    @property
    def key(self) -> str:
        return "system_prompt"

    @property
    def update_command(self) -> str:
        return "review changes (informational)"

    def get_installed_version(self) -> str:
        """Return the last-reviewed prompt version."""
        cache = _PromptCache()
        state = cache.read()
        reviewed = state.get("reviewed_version", "")
        if reviewed:
            return reviewed
        # First run: use current CC version as baseline
        cc_ver = _get_cc_version()
        if cc_ver:
            available = _get_available_versions()
            return _find_prompt_version(cc_ver, available)
        return ""

    def get_latest_version(self) -> str:
        """Return the prompt version matching the current CC install."""
        cc_ver = _get_cc_version()
        if not cc_ver:
            return ""
        available = _get_available_versions()
        if not available:
            return ""
        return _find_prompt_version(cc_ver, available)

    def get_changelog_delta(self, from_ver: str, to_ver: str) -> str:
        """Fetch both prompts and generate a section-level diff."""
        old_prompt = _fetch_prompt(from_ver)
        new_prompt = _fetch_prompt(to_ver)

        if not old_prompt or not new_prompt:
            return f"Could not fetch prompts for comparison ({from_ver} -> {to_ver})"

        header = f"System prompt diff: {from_ver} -> {to_ver}\n"
        diff = _diff_sections(old_prompt, new_prompt)

        # Check for custom prompt
        custom = _detect_custom_prompt()
        if custom:
            header += f"Custom override active: {custom}\n"

        return header + diff

    def get_releases(self, limit: int = 5) -> list[ReleaseInfo]:
        """Return recent prompt versions with section-level change summaries."""
        available = _get_available_versions()
        if not available:
            return []

        recent = available[-limit:]
        releases: list[ReleaseInfo] = []
        prev_prompt = ""

        for ver in recent:
            prompt = _fetch_prompt(ver)
            body = ""
            if prev_prompt and prompt:
                body = _diff_sections(prev_prompt, prompt)
            elif prompt:
                body = f"({len(prompt.splitlines())} lines)"
            prev_prompt = prompt
            releases.append(ReleaseInfo(version=ver, date="", body=body))

        releases.reverse()
        return releases

    def apply_update(self) -> bool:
        """Mark current prompt version as reviewed."""
        cc_ver = _get_cc_version()
        available = _get_available_versions()
        if not cc_ver or not available:
            return False

        prompt_ver = _find_prompt_version(cc_ver, available)
        prompt_text = _fetch_prompt(prompt_ver)
        if not prompt_text:
            return False

        cache = _PromptCache()
        cache.mark_reviewed(prompt_ver, _prompt_hash(prompt_text))
        return True

    def check_status(self) -> VersionInfo:
        """Override to enrich with custom prompt info."""
        info = super().check_status()

        # Add custom prompt indicator to changelog_delta
        custom = _detect_custom_prompt()
        if custom:
            info.changelog_delta = f"Custom: {custom}"

        return info
