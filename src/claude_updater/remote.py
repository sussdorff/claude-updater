"""Remote version checking and updating via SSH.

Each remote adapter is configured with a single command that follows
the convention:
  <command> --version  → prints version to stdout
  <command>            → applies an update (no args)

Example config:
    [adapters.dolt.remote]
    command = "ssh elysium 'pct exec 116 -- /usr/local/bin/dolt-update.sh'"

    [adapters.claude_mem.remote]
    command = "ssh elysium 'pct exec 116 -- /opt/claude-mem/update.sh'"
    parse_mode = "json"
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Literal

from claude_updater.display import DIM, GREEN, NC, RED, YELLOW


@dataclass
class RemoteConfig:
    adapter_key: str
    command: str
    parse_mode: Literal["regex", "json"] = "regex"
    version_regex: str = r"\d+\.\d+\.\d+"
    timeout: int = 30
    update_timeout: int = 120
    enabled: bool = True


@dataclass
class RemoteResult:
    adapter_key: str
    remote_version: str = ""
    error: str = ""
    stdout: str = ""


def load_remote_configs(config: dict) -> dict[str, RemoteConfig]:
    """Load remote config sections from adapter configs.

    Expected TOML format:
        [adapters.dolt.remote]
        command = "ssh elysium 'pct exec 116 -- /usr/local/bin/dolt-update.sh'"
        parse_mode = "regex"
        timeout = 30
    """
    configs: dict[str, RemoteConfig] = {}
    adapters = config.get("adapters", {})
    for key, adapter_cfg in adapters.items():
        if not isinstance(adapter_cfg, dict):
            continue
        remote = adapter_cfg.get("remote")
        if not isinstance(remote, dict):
            continue
        command = remote.get("command", "")
        if not command:
            continue
        rc = RemoteConfig(
            adapter_key=key,
            command=command,
            parse_mode=remote.get("parse_mode", "regex"),
            version_regex=remote.get("version_regex", r"\d+\.\d+\.\d+"),
            timeout=remote.get("timeout", 30),
            update_timeout=remote.get("update_timeout", 120),
            enabled=remote.get("enabled", True),
        )
        if rc.enabled:
            configs[key] = rc
    return configs


def run_remote_check(rc: RemoteConfig) -> RemoteResult:
    """Execute a remote version check via '<command> --version'."""
    version_cmd = f"{rc.command} --version"
    try:
        result = subprocess.run(
            version_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=rc.timeout,
        )
        if result.returncode != 0:
            return RemoteResult(
                adapter_key=rc.adapter_key,
                error=_stderr_summary(result.stderr, result.returncode),
            )

        stdout = result.stdout.strip()
        if rc.parse_mode == "json":
            version = _extract_version_json(stdout)
        else:
            version = _extract_version_regex(stdout, rc.version_regex)

        if not version:
            return RemoteResult(
                adapter_key=rc.adapter_key,
                error="no version found in output",
            )
        return RemoteResult(adapter_key=rc.adapter_key, remote_version=version)

    except subprocess.TimeoutExpired:
        return RemoteResult(
            adapter_key=rc.adapter_key,
            error=f"timeout after {rc.timeout}s",
        )
    except FileNotFoundError as e:
        return RemoteResult(adapter_key=rc.adapter_key, error=str(e))


def run_all_remote_checks(
    configs: dict[str, RemoteConfig],
) -> dict[str, RemoteResult]:
    """Run all remote version checks in parallel."""
    if not configs:
        return {}

    results: dict[str, RemoteResult] = {}
    with ThreadPoolExecutor(max_workers=len(configs)) as pool:
        futures = {
            pool.submit(run_remote_check, rc): key
            for key, rc in configs.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            results[key] = future.result()
    return results


def run_remote_update(rc: RemoteConfig, adapter_name: str) -> RemoteResult:
    """Execute a remote update via '<command>' (no args)."""
    print(f"  {DIM}Updating {adapter_name} remote: {rc.command}{NC}")
    try:
        result = subprocess.run(
            rc.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=rc.update_timeout,
        )
        stdout = result.stdout.strip()
        if result.returncode == 0:
            # Extract new version from update output
            if rc.parse_mode == "json":
                version = _extract_version_json(stdout)
            else:
                version = _extract_version_regex(stdout, rc.version_regex)
            # Show last non-empty line as status
            last_line = _last_nonempty_line(stdout)
            if last_line:
                print(f"  {GREEN}✓{NC} {last_line}")
            else:
                print(f"  {GREEN}✓{NC} Remote update completed")
            return RemoteResult(
                adapter_key=rc.adapter_key,
                remote_version=version,
                stdout=stdout,
            )
        else:
            error_msg = _stderr_summary(result.stderr, result.returncode)
            print(
                f"  {YELLOW}⚠ Remote update failed (exit {result.returncode}): {error_msg}{NC}",
                file=sys.stderr,
            )
            return RemoteResult(
                adapter_key=rc.adapter_key, error=error_msg, stdout=stdout
            )

    except subprocess.TimeoutExpired:
        error = f"timeout after {rc.update_timeout}s"
        print(f"  {YELLOW}⚠ Remote update {error}{NC}", file=sys.stderr)
        return RemoteResult(adapter_key=rc.adapter_key, error=error)
    except FileNotFoundError as e:
        print(f"  {YELLOW}⚠ Remote command not found: {e}{NC}", file=sys.stderr)
        return RemoteResult(adapter_key=rc.adapter_key, error=str(e))


def run_post_local_remote_updates(
    configs: dict[str, RemoteConfig],
    updated_keys: list[str],
    adapter_names: dict[str, str],
) -> dict[str, RemoteResult]:
    """Run remote updates for adapters that were just updated locally (in parallel)."""
    to_run = {key: configs[key] for key in updated_keys if key in configs}
    if not to_run:
        return {}

    results: dict[str, RemoteResult] = {}
    with ThreadPoolExecutor(max_workers=len(to_run)) as pool:
        futures = {
            pool.submit(run_remote_update, rc, adapter_names.get(key, key)): key
            for key, rc in to_run.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            results[key] = future.result()
    return results


def _extract_version_regex(stdout: str, pattern: str) -> str:
    """Extract first version match from stdout using regex."""
    m = re.search(pattern, stdout)
    return m.group(0) if m else ""


def _extract_version_json(stdout: str) -> str:
    """Extract version from JSON output."""
    try:
        data = json.loads(stdout)
        return str(data["version"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return ""


def _last_nonempty_line(text: str) -> str:
    """Return the last non-empty line of text, or empty string."""
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()
    return ""


def _stderr_summary(stderr: str, returncode: int) -> str:
    """Return last line of stderr, or 'exit N' fallback."""
    lines = stderr.strip().splitlines()
    return lines[-1] if lines else f"exit {returncode}"
