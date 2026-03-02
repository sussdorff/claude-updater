from __future__ import annotations

import json
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class VersionInfo:
    tool_name: str
    key: str
    installed_version: str
    latest_version: str
    has_update: bool
    update_method: str
    changelog_delta: str = ""


@dataclass
class ReleaseInfo:
    version: str
    date: str  # ISO format YYYY-MM-DD
    body: str


class ToolAdapter(ABC):
    def __init__(self) -> None:
        self._settings: dict = {}

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def key(self) -> str: ...

    @abstractmethod
    def get_installed_version(self) -> str: ...

    @abstractmethod
    def get_latest_version(self) -> str: ...

    @abstractmethod
    def get_changelog_delta(self, from_ver: str, to_ver: str) -> str: ...

    @abstractmethod
    def apply_update(self) -> bool: ...

    def get_releases(self, limit: int = 5) -> list[ReleaseInfo]:
        """Return recent releases with version, date, and body.

        Override in subclasses. Default returns empty list.
        """
        return []

    @property
    def update_command(self) -> str:
        """Human-readable update method description."""
        return ""

    def has_update(self) -> bool:
        return self.get_installed_version() != self.get_latest_version()

    def check_status(self) -> VersionInfo:
        installed = self.get_installed_version()
        latest = self.get_latest_version()
        update = installed != latest and bool(installed) and bool(latest)
        return VersionInfo(
            tool_name=self.name,
            key=self.key,
            installed_version=installed,
            latest_version=latest,
            has_update=update,
            update_method=self.update_command if update else "",
            changelog_delta="",
        )

    def configure(self, settings: dict) -> None:
        self._settings = settings


def gh_get_releases(repo: str, limit: int = 5) -> list[ReleaseInfo]:
    """Fetch recent releases from a GitHub repo via gh API."""
    try:
        r = subprocess.run(
            ["gh", "api", f"repos/{repo}/releases",
             "--jq", f'[.[:{ limit}][] | {{tag: .tag_name, date: .published_at, body: .body}}]'],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return []

        entries = json.loads(r.stdout)
        releases = []
        for entry in entries:
            version = entry["tag"].lstrip("v")
            date = entry["date"][:10] if entry.get("date") else ""
            body = _extract_changelog_section(entry.get("body", ""))
            releases.append(ReleaseInfo(version=version, date=date, body=body))
        return releases
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return []


def gh_changelog_delta(repo: str, from_ver: str, to_ver: str) -> str:
    """Fetch changelog between two versions from GitHub releases.

    Uses 'gh api' to get release bodies, extracts the Changelog section,
    and returns releases between from_ver (exclusive) and to_ver (inclusive).
    """
    try:
        r = subprocess.run(
            ["gh", "api", f"repos/{repo}/releases", "--paginate",
             "--jq", ".[].tag_name"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return ""

        # Find which tags are in range
        all_tags = r.stdout.strip().splitlines()
        tags_in_range = []
        in_range = False
        for tag in all_tags:
            ver = tag.lstrip("v")
            if ver == to_ver:
                in_range = True
            if in_range:
                tags_in_range.append(tag)
            if ver == from_ver:
                break

        # Exclude from_ver itself (we want changes *since* from_ver)
        if tags_in_range and tags_in_range[-1].lstrip("v") == from_ver:
            tags_in_range = tags_in_range[:-1]

        if not tags_in_range:
            return ""

        # Fetch body for each release in range (limit to 3 to avoid huge output)
        parts = []
        for tag in tags_in_range[:3]:
            try:
                r = subprocess.run(
                    ["gh", "api", f"repos/{repo}/releases/tags/{tag}",
                     "--jq", ".body"],
                    capture_output=True, text=True, timeout=15,
                )
                if r.returncode != 0:
                    continue
                body = _extract_changelog_section(r.stdout)
                if body:
                    parts.append(f"### {tag}\n{body}")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        return "\n\n".join(parts)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _extract_changelog_section(body: str) -> str:
    """Extract the Changelog/What's Changed section from a release body.

    Skips install instructions and binary lists, returns just the meaningful changes.
    """
    lines = body.splitlines()
    result = []
    in_changelog = False

    for line in lines:
        lower = line.lower().strip()
        # Start capturing at changelog-like headers
        if re.match(r"^#{1,3}\s*(changelog|what'?s?\s*changed|changes|features|bug\s*fixes|fixes)", lower):
            in_changelog = True
            continue
        # Stop at non-changelog sections
        if in_changelog and re.match(r"^#{1,3}\s*(install|download|binary|pre-compiled|full\s*diff|new\s*contributor)", lower):
            break
        if in_changelog and line.strip():
            result.append(line)

    # If no explicit section found, try to grab commit-style entries
    if not result:
        for line in lines:
            if line.strip().startswith("* ") or line.strip().startswith("- "):
                result.append(line)
            if len(result) >= 20:
                break

    # Truncate to keep output reasonable
    if len(result) > 30:
        result = result[:30]
        result.append("  ...")

    return "\n".join(result).strip()


def changelog_get_releases(changelog_path: str, git_dir: str, limit: int = 5) -> list[ReleaseInfo]:
    """Parse a CHANGELOG.md file into ReleaseInfo entries.

    Uses git log to find commit dates for version headings.
    """
    from pathlib import Path

    path = Path(changelog_path)
    if not path.exists():
        return []

    try:
        text = path.read_text()
    except OSError:
        return []

    # Parse sections: ## [version] or ## version
    releases: list[ReleaseInfo] = []
    current_version = ""
    current_lines: list[str] = []

    for line in text.splitlines():
        match = re.match(r"^##\s+\[?v?(\d+\.\d+[^\]]*)\]?", line)
        if match:
            if current_version:
                releases.append(ReleaseInfo(
                    version=current_version,
                    date="",
                    body="\n".join(current_lines).strip(),
                ))
                if len(releases) >= limit:
                    break
            current_version = match.group(1)
            current_lines = []
        elif current_version:
            current_lines.append(line)

    # Don't forget the last section
    if current_version and len(releases) < limit:
        releases.append(ReleaseInfo(
            version=current_version,
            date="",
            body="\n".join(current_lines).strip(),
        ))

    # Try to get dates from git log for each version
    for release in releases:
        try:
            r = subprocess.run(
                ["git", "-C", git_dir, "log", "--all", "--format=%aI",
                 f"--grep=v{release.version}", "-1"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip():
                release.date = r.stdout.strip()[:10]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return releases
