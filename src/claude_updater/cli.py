"""CLI entry points for claude-updater."""

from __future__ import annotations

import argparse
import sys

from claude_updater import __version__


def cmd_check(args: argparse.Namespace) -> None:
    from claude_updater.config import load_config
    from claude_updater.runner import run_check

    config = load_config()
    run_check(config, force=args.force, json_output=args.json)


def cmd_update(args: argparse.Namespace) -> None:
    from claude_updater.config import load_config
    from claude_updater.runner import run_update

    config = load_config()
    run_update(config, auto_yes=args.yes)


def cmd_config_init(args: argparse.Namespace) -> None:
    from claude_updater.config import init_config

    try:
        path = init_config()
        print(f"Config created at: {path}")
    except FileExistsError:
        print(f"Config already exists. Edit it directly or delete to re-initialize.",
              file=sys.stderr)
        sys.exit(1)


def cmd_config_show(args: argparse.Namespace) -> None:
    from claude_updater.config import get_config_path, load_config

    path = get_config_path()
    if path.exists():
        print(f"Config file: {path}\n")
        print(path.read_text())
    else:
        print(f"No config file found at {path}")
        print("Run 'claude-updater config init' to create one.")


def cmd_list(args: argparse.Namespace) -> None:
    from claude_updater.adapters import ADAPTER_REGISTRY
    from claude_updater.config import load_config

    config = load_config()
    adapter_configs = config.get("adapters", {})

    print(f"{'Adapter':<20} {'Enabled':<10}")
    print(f"{'─' * 20} {'─' * 10}")
    for key, cls in ADAPTER_REGISTRY.items():
        adapter_cfg = adapter_configs.get(key, {})
        enabled = adapter_cfg.get("enabled", True)
        status = "✓" if enabled else "✗"
        adapter = cls()
        print(f"{adapter.name:<20} {status}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="claude-updater",
        description="Multi-tool update checker for the Claude Code ecosystem",
    )
    parser.add_argument("--version", action="version", version=f"claude-updater {__version__}")

    sub = parser.add_subparsers(dest="command")

    # check
    check_p = sub.add_parser("check", help="Check for updates")
    check_p.add_argument("--force", action="store_true", help="Ignore cache")
    check_p.add_argument("--json", action="store_true", help="JSON output")
    check_p.set_defaults(func=cmd_check)

    # update
    update_p = sub.add_parser("update", help="Check and apply updates")
    update_p.add_argument("--yes", "-y", action="store_true", help="Auto-approve updates")
    update_p.set_defaults(func=cmd_update)

    # config
    config_p = sub.add_parser("config", help="Configuration management")
    config_sub = config_p.add_subparsers(dest="config_command")
    init_p = config_sub.add_parser("init", help="Create default config")
    init_p.set_defaults(func=cmd_config_init)
    show_p = config_sub.add_parser("show", help="Show current config")
    show_p.set_defaults(func=cmd_config_show)

    # list
    list_p = sub.add_parser("list", help="List available adapters")
    list_p.set_defaults(func=cmd_list)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
