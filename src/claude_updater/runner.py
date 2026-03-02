"""Orchestrator: parallel collect → display → AI analysis → prompt → apply."""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from claude_updater.adapters import get_enabled_adapters
from claude_updater.adapters.base import ToolAdapter, VersionInfo
from claude_updater.cache import VersionCache
from claude_updater.config import load_config
from claude_updater.display import (
    BLUE,
    GREEN,
    NC,
    display_analysis,
    display_summary,
    prompt_for_update,
    warn_running_instances,
)


def _refresh_brew_index() -> None:
    """Run 'brew update' to refresh the local formula index.

    Without this, 'brew info --json=v2' returns stale version data
    and brew-based adapters miss available updates.
    """
    try:
        subprocess.run(
            ["brew", "update"],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def _check_adapter(adapter: ToolAdapter) -> VersionInfo:
    """Check a single adapter for updates."""
    try:
        return adapter.check_status()
    except Exception as e:
        return VersionInfo(
            tool_name=adapter.name,
            key=adapter.key,
            installed_version="error",
            latest_version="",
            has_update=False,
            update_method="",
            changelog_delta=str(e),
        )


def run_check(
    config: dict | None = None,
    force: bool = False,
    json_output: bool = False,
) -> list[VersionInfo]:
    """Run update checks for all enabled adapters."""
    if config is None:
        config = load_config()

    cache = VersionCache(ttl=config.get("general", {}).get("cache_ttl", 86400))

    # Check cache unless forced
    if not force and cache.is_fresh():
        cached = cache.read()
        if cached.get("versions") and not json_output:
            results = []
            for key, data in cached["versions"].items():
                results.append(VersionInfo(
                    tool_name=data.get("tool_name", key),
                    key=key,
                    installed_version=data.get("installed", ""),
                    latest_version=data.get("latest", ""),
                    has_update=data.get("has_update", False),
                    update_method=data.get("update_method", ""),
                ))
            has_updates = display_summary(results)
            if not has_updates:
                return results
            return results

    adapters = get_enabled_adapters(config)

    # Refresh Homebrew index so brew-based adapters see latest versions
    _refresh_brew_index()

    # Parallel version checks
    results: list[VersionInfo] = []
    with ThreadPoolExecutor(max_workers=len(adapters)) as pool:
        futures = {pool.submit(_check_adapter, a): a for a in adapters}
        for future in as_completed(futures):
            results.append(future.result())

    # Sort by adapter order in registry
    adapter_order = [a.key for a in adapters]
    results.sort(key=lambda r: adapter_order.index(r.key) if r.key in adapter_order else 999)

    # Cache results
    cache_data = {}
    for r in results:
        cache_data[r.key] = {
            "tool_name": r.tool_name,
            "installed": r.installed_version,
            "latest": r.latest_version,
            "has_update": r.has_update,
            "update_method": r.update_method,
        }
    cache.write(cache_data)

    if json_output:
        print(json.dumps(cache_data, indent=2))
        return results

    display_summary(results)
    return results


def run_update(config: dict | None = None, auto_yes: bool = False) -> None:
    """Run checks and optionally apply updates."""
    if config is None:
        config = load_config()

    results = run_check(config, force=True)
    updatable = [r for r in results if r.has_update and r.update_method]

    if not updatable:
        return

    # Fetch changelogs for updatable tools
    adapters = get_enabled_adapters(config)
    adapter_map = {a.key: a for a in adapters}
    changelogs: dict[str, str] = {}

    for info in updatable:
        adapter = adapter_map.get(info.key)
        if adapter and info.installed_version and info.latest_version:
            delta = adapter.get_changelog_delta(info.installed_version, info.latest_version)
            if delta:
                changelogs[info.tool_name] = delta
                info.changelog_delta = delta

    # AI analysis if configured and changelogs available
    ai_config = config.get("ai_analysis", {})
    if ai_config.get("enabled") and changelogs:
        try:
            from claude_updater.analyzer import analyze_changelogs
            analysis = analyze_changelogs(changelogs, ai_config)
            if analysis:
                display_analysis(analysis)
        except Exception:
            pass

    # Prompt for update
    if auto_yes:
        answer = "yes"
    else:
        answer = prompt_for_update()

    if answer != "yes":
        return

    # Apply updates
    for info in updatable:
        adapter = adapter_map.get(info.key)
        if adapter:
            print(f"{BLUE}Updating {info.tool_name}...{NC}")
            success = adapter.apply_update()
            if success:
                new_ver = adapter.get_installed_version()
                print(f"{GREEN}{info.tool_name} updated to {new_ver}{NC}")
            else:
                print(f"Failed to update {info.tool_name}", file=sys.stderr)

    warn_running_instances()
