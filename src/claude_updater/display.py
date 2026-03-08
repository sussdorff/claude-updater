"""Terminal output formatting and interactive prompts."""

from __future__ import annotations

import os
import sys

from claude_updater.adapters.base import VersionInfo

# ANSI colors (disabled when NO_COLOR is set)
_no_color = os.environ.get("NO_COLOR") is not None

# Use ASCII fallback for terminals that can't handle Unicode chars (e.g. Windows cp1252)
def _safe_char(unicode_char: str, ascii_fallback: str) -> str:
    try:
        unicode_char.encode(sys.stdout.encoding or "utf-8")
        return unicode_char
    except (UnicodeEncodeError, LookupError):
        return ascii_fallback

_HLINE = _safe_char("─", "-")
_BULLET = _safe_char("●", "*")
_CHECK = _safe_char("✓", "+")
_ARROW = _safe_char("→", "->")
_WARN = _safe_char("⚠", "!")

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
    print(f"{DIM}{_HLINE * 40}{NC}")

    for info in results:
        if not info.installed_version:
            print(f"{DIM}?{NC} {info.tool_name}: not found")
            continue

        if info.has_update:
            has_updates = True
            line = f"{YELLOW}{_BULLET}{NC} {info.tool_name}: {info.installed_version} {_ARROW}{info.latest_version}"
        else:
            line = f"{GREEN}{_CHECK}{NC} {info.tool_name}: {info.installed_version}"

        if show_remote and info.remote_version:
            drift = info.remote_version != info.installed_version
            dot = f" {YELLOW}{_BULLET}{NC}" if drift else ""
            line += f"  {DIM}remote:{NC} {info.remote_version}{dot}"

        print(line)

    print(f"{DIM}{_HLINE * 40}{NC}")
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
            print(f"{DIM}{_HLINE * 40}{NC}")
            print(f"{CYAN}{info.tool_name}{NC} {info.installed_version} {_ARROW}{info.latest_version}")
            print()
            # Indent and dim the changelog body
            for line in info.changelog_delta.splitlines():
                print(f"  {line}")
    if shown:
        print(f"{DIM}{_HLINE * 40}{NC}")


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
        print(f"{DIM}{_HLINE * 40}{NC}")
        print(f"{CYAN}{name}{NC}")
        for release in releases:
            print(f"\n  {BOLD}{release['version']}{NC} {DIM}({release.get('date', '?')}){NC}")
            if release.get("body"):
                for line in release["body"].splitlines():
                    print(f"  {line}")
    print(f"{DIM}{_HLINE * 40}{NC}")


def prompt_for_update(timeout: int = 15) -> str:
    """Ask user whether to apply updates. Returns 'yes', 'no', or 'later'."""
    if not sys.stdin.isatty():
        return "later"

    try:
        print()
        sys.stdout.write(
            f"Apply updates? [{BOLD}Y{NC}]es / [n]o / [l]ater ({timeout}s timeout {_ARROW}later): "
        )
        sys.stdout.flush()

        if sys.platform == "win32":
            # select.select() doesn't work on stdin on Windows
            import msvcrt
            import time

            start = time.monotonic()
            chars: list[str] = []
            while time.monotonic() - start < timeout:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch in ("\r", "\n"):
                        print()
                        break
                    chars.append(ch)
                    sys.stdout.write(ch)
                    sys.stdout.flush()
                else:
                    time.sleep(0.1)
            else:
                print()
                return "later"

            answer = "".join(chars).strip().lower()
        else:
            import select
            ready, _, _ = select.select([sys.stdin], [], [], timeout)
            if ready:
                answer = sys.stdin.readline().strip().lower()
            else:
                print()
                return "later"

        if answer in ("y", "yes", ""):
            return "yes"
        elif answer in ("n", "no"):
            return "no"
        return "later"
    except (EOFError, KeyboardInterrupt):
        print()
        return "later"


def warn_running_instances() -> None:
    """Warn if multiple Claude instances are running."""
    import subprocess
    try:
        if sys.platform == "win32":
            r = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq claude.exe", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            # Each running instance produces a line with the process name
            pids = [
                line for line in r.stdout.strip().splitlines()
                if "claude" in line.lower() and "INFO:" not in line
            ]
        else:
            r = subprocess.run(
                ["pgrep", "-f", "claude"],
                capture_output=True, text=True, timeout=5,
            )
            pids = [p for p in r.stdout.strip().splitlines() if p]
        if len(pids) > 1:
            print(f"{YELLOW}{_WARN} {len(pids)} Claude instances running - restart them after updates{NC}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
