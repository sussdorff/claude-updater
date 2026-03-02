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


def _clean_body(text: str) -> str:
    """Strip noise from release body text to keep output concise for agents.

    Removes HTML tags, dependabot boilerplate, code blocks, markdown images,
    and condenses PR entries to title + sub-bullets only.
    """
    lines = text.splitlines()
    cleaned: list[str] = []
    in_code_block = False
    in_html_details = False
    skip_dependabot = False

    for line in lines:
        stripped = line.strip()

        # Toggle code blocks — skip entirely
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Skip HTML <details> blocks (dependabot, etc.)
        if "<details>" in stripped:
            in_html_details = True
            continue
        if "</details>" in stripped:
            in_html_details = False
            continue
        if in_html_details:
            continue

        # Skip HTML tags, markdown images, comment markers, horizontal rules
        if re.match(r"^\s*<(br|ul|/ul|li|/li|a |/a|summary|/summary)", stripped):
            continue
        if stripped.startswith("[![") or stripped.startswith("[//]: #"):
            continue
        if stripped == "---":
            continue

        # Skip dependabot boilerplate lines
        if "@dependabot" in stripped:
            skip_dependabot = True
            continue
        if skip_dependabot:
            if stripped.startswith("- `@dependabot") or stripped.startswith("You can"):
                continue
            skip_dependabot = False

        # Skip empty lines in PR descriptions (keep structure compact)
        if not stripped:
            continue

        # Keep PR title lines (* [...]) and sub-bullets (- ...)
        # For continuation lines (indented text that isn't a sub-bullet),
        # keep only the first one as a brief description
        cleaned.append(line)

    return "\n".join(cleaned)


def _condense_pr_entries(text: str) -> str:
    """Condense PR entries: keep title line + first description line + sub-bullets."""
    lines = text.splitlines()
    result: list[str] = []
    saw_description_for_current_pr = False

    for line in lines:
        stripped = line.strip()
        # PR title line
        if re.match(r"^\* \[", stripped):
            result.append(line)
            saw_description_for_current_pr = False
            continue
        # Sub-bullet under a PR
        if stripped.startswith("- "):
            result.append(line)
            continue
        # First continuation/description line for this PR — keep it
        if not saw_description_for_current_pr and stripped:
            result.append(line)
            saw_description_for_current_pr = True
            continue
        # Non-PR lines (intro text etc.) — always keep
        if not line.startswith("  "):
            result.append(line)
            saw_description_for_current_pr = False

    return "\n".join(result)


def _extract_changelog_section(body: str) -> str:
    """Extract meaningful changelog content from a release body.

    Handles two styles:
    - Standard: sections like "Changelog", "What's Changed", etc.
    - Dolt-style: intro text + "# Merged PRs" with sub-repo sections (## dolt, ## go-mysql-server).
      For dolt-style, captures intro text and only the "## dolt" subsection.

    Post-processes to strip HTML, dependabot noise, and condense PR descriptions.
    """
    lines = body.splitlines()
    result = []

    # --- Dolt-style: intro + "# Merged PRs" with sub-repo sections ---
    has_merged_prs = any(re.match(r"^#\s+Merged PRs", line, re.IGNORECASE) for line in lines)
    if has_merged_prs:
        # Capture intro text (before first # heading)
        intro = []
        for line in lines:
            if line.startswith("#"):
                break
            if line.strip():
                intro.append(line)

        # Capture only the "## dolt" subsection under "# Merged PRs"
        in_merged = False
        in_dolt_section = False
        dolt_entries = []
        for line in lines:
            if re.match(r"^#\s+Merged PRs", line, re.IGNORECASE):
                in_merged = True
                continue
            if in_merged:
                # New top-level heading ends merged PRs
                if re.match(r"^#\s+", line) and not re.match(r"^##", line):
                    break
                if re.match(r"^##\s+dolt\b", line, re.IGNORECASE):
                    in_dolt_section = True
                    continue
                if re.match(r"^##\s+", line) and in_dolt_section:
                    break  # hit next sub-repo section
                if in_dolt_section:
                    dolt_entries.append(line)

        if intro:
            result.extend(intro)
            if dolt_entries:
                result.append("")
        result.extend(dolt_entries)

        raw = "\n".join(result).strip()
        cleaned = _condense_pr_entries(_clean_body(raw))
        return _truncate(cleaned)

    # --- Standard style: explicit changelog/changes sections ---
    in_changelog = False
    for line in lines:
        lower = line.lower().strip()
        if re.match(r"^#{1,3}\s*(changelog|what'?s?\s*changed|changes|features|bug\s*fixes|fixes)", lower):
            in_changelog = True
            continue
        if in_changelog and re.match(r"^#{1,3}\s*(install|download|binary|pre-compiled|full\s*diff|new\s*contributor)", lower):
            break
        if in_changelog and line.strip():
            result.append(line)

    # Fallback: grab bullet-point entries
    if not result:
        for line in lines:
            if line.strip().startswith("* ") or line.strip().startswith("- "):
                result.append(line)
            if len(result) >= 20:
                break

    raw = "\n".join(result).strip()
    cleaned = _condense_pr_entries(_clean_body(raw))
    return _truncate(cleaned)


def _truncate(text: str, max_lines: int = 30) -> str:
    """Truncate text to max_lines, appending '...' if trimmed."""
    lines = text.splitlines()
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + "\n  ..."
    return text


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
