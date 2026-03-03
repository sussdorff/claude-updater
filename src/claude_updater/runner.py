"""Orchestrator: parallel collect → display → prompt → apply."""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from claude_updater.adapters import get_enabled_adapters
from claude_updater.adapters.base import ToolAdapter, VersionInfo
from claude_updater.cache import ReleaseNotesCache, VersionCache
from claude_updater.config import load_config
from claude_updater.display import (
    BLUE,
    GREEN,
    NC,
    display_changelogs,
    display_release_notes,
    display_summary,
    prompt_for_update,
    warn_running_instances,
)
from claude_updater.hooks import load_hooks, run_post_update_hooks
from claude_updater.remote import (
    load_remote_configs,
    run_all_remote_checks,
    run_post_local_remote_updates,
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


def _fetch_changelogs(
    results: list[VersionInfo],
    config: dict,
) -> dict[str, str]:
    """Fetch changelog deltas for tools with updates. Returns {tool_name: changelog}."""
    adapters = get_enabled_adapters(config)
    adapter_map = {a.key: a for a in adapters}
    changelogs: dict[str, str] = {}

    updatable = [r for r in results if r.has_update]
    for info in updatable:
        adapter = adapter_map.get(info.key)
        if adapter and info.installed_version and info.latest_version:
            delta = adapter.get_changelog_delta(info.installed_version, info.latest_version)
            if delta:
                changelogs[info.tool_name] = delta
                info.changelog_delta = delta

    return changelogs


def run_check(
    config: dict | None = None,
    force: bool = False,
    json_output: bool = False,
    show_notes: bool = False,
    remote: bool = False,
) -> list[VersionInfo]:
    """Run update checks for all enabled adapters."""
    if config is None:
        config = load_config()

    cache = VersionCache(ttl=config.get("general", {}).get("cache_ttl", 86400))

    # Check cache unless forced
    if not force and not show_notes and cache.is_fresh():
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
                    remote_version=data.get("remote", ""),
                ))
            if remote:
                _merge_remote_versions(results, config)
            display_summary(results, show_remote=remote)
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

    # Merge remote versions if requested
    if remote:
        _merge_remote_versions(results, config)

    # Cache results
    cache_data = {}
    for r in results:
        entry: dict = {
            "tool_name": r.tool_name,
            "installed": r.installed_version,
            "latest": r.latest_version,
            "has_update": r.has_update,
            "update_method": r.update_method,
        }
        if r.remote_version:
            entry["remote"] = r.remote_version
        cache_data[r.key] = entry
    cache.write(cache_data)

    if json_output:
        print(json.dumps(cache_data, indent=2))
        return results

    has_updates = display_summary(results, show_remote=remote)

    # Show release notes when updates are available (or when --notes is passed)
    if has_updates or show_notes:
        changelogs = _fetch_changelogs(results, config)
        if changelogs:
            display_changelogs(results)

    return results


def _merge_remote_versions(results: list[VersionInfo], config: dict) -> None:
    """Run remote checks and merge versions into results in-place."""
    remote_configs = load_remote_configs(config)
    if not remote_configs:
        return
    checks = run_all_remote_checks(remote_configs)
    for r in results:
        check = checks.get(r.key)
        if check and check.remote_version:
            r.remote_version = check.remote_version


def run_update(
    config: dict | None = None,
    auto_yes: bool = False,
    remote: bool = False,
) -> None:
    """Run checks and optionally apply updates."""
    if config is None:
        config = load_config()

    results = run_check(config, force=True, show_notes=True, remote=remote)
    updatable = [r for r in results if r.has_update and r.update_method]

    # Check for remote drift (remote version behind local installed)
    remote_configs = load_remote_configs(config) if remote else {}
    remote_drift = []
    if remote_configs:
        for r in results:
            if r.remote_version and r.remote_version != r.installed_version:
                if r.key in remote_configs:
                    remote_drift.append(r)

    if not updatable and not remote_drift:
        return

    # Prompt for update
    if auto_yes:
        answer = "yes"
    else:
        answer = prompt_for_update()

    if answer != "yes":
        return

    # Apply local updates
    hooks = load_hooks(config)
    adapters = get_enabled_adapters(config)
    adapter_map = {a.key: a for a in adapters}
    updated_keys: list[str] = []
    adapter_names: dict[str, str] = {a.key: a.name for a in adapters}

    for info in updatable:
        adapter = adapter_map.get(info.key)
        if adapter:
            print(f"{BLUE}Updating {info.tool_name}...{NC}")
            success = adapter.apply_update()
            if success:
                new_ver = adapter.get_installed_version()
                print(f"{GREEN}{info.tool_name} updated to {new_ver}{NC}")
                updated_keys.append(info.key)
                run_post_update_hooks(hooks, info.key, info.tool_name)
            else:
                print(f"Failed to update {info.tool_name}", file=sys.stderr)

    # Apply remote updates for locally-updated adapters + drifted remotes
    if remote_configs:
        keys_to_update_remote = list(set(
            updated_keys + [r.key for r in remote_drift]
        ))
        if keys_to_update_remote:
            run_post_local_remote_updates(
                remote_configs, keys_to_update_remote, adapter_names
            )

    warn_running_instances()


def _fetch_releases(adapter: ToolAdapter, cache: ReleaseNotesCache) -> tuple[str, list[dict]]:
    """Fetch releases for a single adapter and merge into cache."""
    try:
        releases = adapter.get_releases(limit=5)
        new_entries = [
            {"version": r.version, "date": r.date, "body": r.body}
            for r in releases
        ]
        merged = cache.merge(adapter.key, new_entries)
        return adapter.key, merged
    except Exception:
        # Fall back to cached data
        return adapter.key, cache.read(adapter.key)


def run_release_notes(
    config: dict | None = None,
    days: int = 3,
    tool_filter: str | None = None,
    json_output: bool = False,
) -> dict[str, list[dict]]:
    """Fetch and display release notes for all enabled adapters."""
    if config is None:
        config = load_config()

    adapters = get_enabled_adapters(config)
    if tool_filter:
        adapters = [a for a in adapters if a.key == tool_filter or a.name.lower() == tool_filter.lower()]
        if not adapters:
            print(f"Unknown tool: {tool_filter}", file=sys.stderr)
            sys.exit(1)

    cache = ReleaseNotesCache()

    # Parallel fetch
    all_releases: dict[str, list[dict]] = {}
    adapter_names: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(adapters)) as pool:
        futures = {pool.submit(_fetch_releases, a, cache): a for a in adapters}
        for future in as_completed(futures):
            adapter = futures[future]
            key, releases = future.result()
            all_releases[key] = releases
            adapter_names[key] = adapter.name

    # Filter by date
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    filtered: dict[str, list[dict]] = {}
    for key, releases in all_releases.items():
        recent = [r for r in releases if r.get("date", "") >= cutoff]
        if recent:
            filtered[key] = recent

    if json_output:
        output = {
            adapter_names.get(k, k): releases
            for k, releases in filtered.items()
        }
        print(json.dumps(output, indent=2))
    else:
        display_release_notes(filtered, adapter_names, days)

    return filtered
