"""Post-update hook execution."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from claude_updater.display import DIM, GREEN, NC, YELLOW
from claude_updater.remote import _last_nonempty_line, _stderr_summary


@dataclass
class HookConfig:
    adapter: str  # adapter key or "*" for all
    command: str
    enabled: bool = True
    timeout: int = 120


def load_hooks(config: dict) -> list[HookConfig]:
    """Load hook definitions from config dict.

    Expected TOML format:
        [[hooks.post_update]]
        adapter = "claude_mem"
        command = "ssh elysium 'pct exec 116 -- /opt/claude-mem/update.sh'"
        enabled = true
        timeout = 120
    """
    hooks_section = config.get("hooks", {})
    raw_hooks = hooks_section.get("post_update", [])

    hooks = []
    for entry in raw_hooks:
        if not isinstance(entry, dict):
            continue
        adapter = entry.get("adapter", "*")
        command = entry.get("command", "")
        if not command:
            continue
        hooks.append(HookConfig(
            adapter=adapter,
            command=str(Path(command).expanduser()) if not command.startswith("ssh") else command,
            enabled=entry.get("enabled", True),
            timeout=entry.get("timeout", 120),
        ))
    return hooks


def get_hooks_for_adapter(hooks: list[HookConfig], adapter_key: str) -> list[HookConfig]:
    """Return enabled hooks matching the given adapter key."""
    return [
        h for h in hooks
        if h.enabled and (h.adapter == adapter_key or h.adapter == "*")
    ]


def run_post_update_hooks(
    hooks: list[HookConfig],
    adapter_key: str,
) -> bool:
    """Execute post-update hooks for the given adapter. Returns True if all succeeded."""
    matching = get_hooks_for_adapter(hooks, adapter_key)
    if not matching:
        return True

    all_ok = True
    for hook in matching:
        print(f"  {DIM}Running post-update hook: {hook.command}{NC}")
        try:
            result = subprocess.run(
                hook.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=hook.timeout,
            )
            if result.returncode == 0:
                last_line = _last_nonempty_line(result.stdout)
                if last_line:
                    print(f"  {GREEN}✓{NC} {last_line}")
                else:
                    print(f"  {GREEN}✓{NC} Hook completed")
            else:
                all_ok = False
                print(
                    f"  {YELLOW}⚠ Hook failed (exit {result.returncode}): "
                    f"{_stderr_summary(result.stderr, result.returncode)}{NC}",
                    file=sys.stderr,
                )
        except subprocess.TimeoutExpired:
            all_ok = False
            print(f"  {YELLOW}⚠ Hook timed out after {hook.timeout}s{NC}", file=sys.stderr)
        except FileNotFoundError as e:
            all_ok = False
            print(f"  {YELLOW}⚠ Hook command not found: {e}{NC}", file=sys.stderr)

    return all_ok
