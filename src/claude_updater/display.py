"""Terminal output formatting and interactive prompts."""

from __future__ import annotations

import os
import sys

from claude_updater.adapters.base import VersionInfo

# ANSI colors (disabled when NO_COLOR is set)
_no_color = os.environ.get("NO_COLOR") is not None

def _c(code: str) -> str:
    return "" if _no_color else code

RED = _c("\033[0;31m")
GREEN = _c("\033[0;32m")
YELLOW = _c("\033[0;33m")
BLUE = _c("\033[0;34m")
CYAN = _c("\033[0;36m")
DIM = _c("\033[2m")
BOLD = _c("\033[1m")
NC = _c("\033[0m")


def display_summary(results: list[VersionInfo], show_remote: bool = False) -> bool:
    """Display update summary table. Returns True if any updates available."""
    has_updates = False

    print()
    print(f"{BOLD}Tool Update Check{NC}")
    print(f"{DIM}{'─' * 40}{NC}")

    for info in results:
        if not info.installed_version:
            print(f"{DIM}?{NC} {info.tool_name}: not found")
            continue

        if info.has_update:
            has_updates = True
            line = f"{YELLOW}●{NC} {info.tool_name}: {info.installed_version} → {info.latest_version}"
        else:
            line = f"{GREEN}✓{NC} {info.tool_name}: {info.installed_version}"

        if show_remote and info.remote_version:
            drift = info.remote_version != info.installed_version
            dot = f" {YELLOW}●{NC}" if drift else ""
            line += f"  {DIM}remote:{NC} {info.remote_version}{dot}"

        print(line)

    print(f"{DIM}{'─' * 40}{NC}")
    return has_updates


def display_changelogs(results: list[VersionInfo]) -> None:
    """Display changelog deltas for tools with updates."""
    shown = False
    for info in results:
        if info.has_update and info.changelog_delta:
            if not shown:
                print()
                print(f"{BOLD}Release Notes{NC}")
                shown = True
            print(f"{DIM}{'─' * 40}{NC}")
            print(f"{CYAN}{info.tool_name}{NC} {info.installed_version} → {info.latest_version}")
            print()
            # Indent and dim the changelog body
            for line in info.changelog_delta.splitlines():
                print(f"  {line}")
    if shown:
        print(f"{DIM}{'─' * 40}{NC}")


def display_release_notes(
    filtered: dict[str, list[dict]],
    adapter_names: dict[str, str],
    days: int,
) -> None:
    """Display release notes grouped by tool."""
    if not filtered:
        print(f"\n{DIM}No release notes found for the last {days} day(s).{NC}")
        return

    print()
    print(f"{BOLD}Release Notes{NC} {DIM}(last {days} day{'s' if days != 1 else ''}){NC}")

    for key, releases in filtered.items():
        name = adapter_names.get(key, key)
        print(f"{DIM}{'─' * 40}{NC}")
        print(f"{CYAN}{name}{NC}")
        for release in releases:
            print(f"\n  {BOLD}{release['version']}{NC} {DIM}({release.get('date', '?')}){NC}")
            if release.get("body"):
                for line in release["body"].splitlines():
                    print(f"  {line}")
    print(f"{DIM}{'─' * 40}{NC}")


def prompt_for_update(timeout: int = 15) -> str:
    """Ask user whether to apply updates. Returns 'yes', 'no', or 'later'."""
    if not sys.stdin.isatty():
        return "later"

    try:
        print()
        sys.stdout.write(
            f"Apply updates? [{BOLD}Y{NC}]es / [n]o / [l]ater ({timeout}s timeout → later): "
        )
        sys.stdout.flush()

        import select
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if ready:
            answer = sys.stdin.readline().strip().lower()
            if answer in ("y", "yes", ""):
                return "yes"
            elif answer in ("n", "no"):
                return "no"
            return "later"
        else:
            print()
            return "later"
    except (EOFError, KeyboardInterrupt):
        print()
        return "later"


def warn_running_instances() -> None:
    """Warn if multiple Claude instances are running."""
    import subprocess
    try:
        r = subprocess.run(
            ["pgrep", "-f", "claude"],
            capture_output=True, text=True, timeout=5,
        )
        pids = [p for p in r.stdout.strip().splitlines() if p]
        if len(pids) > 1:
            print(f"{YELLOW}⚠ {len(pids)} Claude instances running — restart them after updates{NC}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
