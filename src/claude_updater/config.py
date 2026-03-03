import os
import tomllib
from pathlib import Path

DEFAULT_CONFIG = """\
[general]
cache_ttl = 86400
check_on_startup = true

[adapters.claude_updater_self]
enabled = true

[adapters.claude_code]
enabled = true

[adapters.claude_mem]
enabled = true
plugin_dir = "~/.claude/plugins/marketplaces/thedotmack"

[adapters.beads_plugin]
enabled = true
plugin_dir = "~/.claude/plugins/marketplaces/beads-marketplace"

[adapters.dolt]
enabled = true

# Remote adapters: check + update remote hosts via SSH.
# Convention: <command> --version → prints version, <command> → runs update.
# parse_mode = "regex" (default) extracts first semver match from stdout.
# parse_mode = "json" expects {"version": "..."} in stdout.
#
# [adapters.dolt.remote]
# command = "ssh elysium 'pct exec 116 -- /usr/local/bin/dolt-update.sh'"
#
# [adapters.claude_mem.remote]
# command = "ssh elysium 'pct exec 116 -- /opt/claude-mem/update.sh'"

# Post-update hooks: commands executed after a tool is successfully updated.
# adapter = "claude_mem" (specific) or "*" (any tool)
# timeout = seconds before hook is killed (default: 120)
#
# [[hooks.post_update]]
# adapter = "claude_mem"
# command = "ssh elysium 'pct exec 116 -- /opt/claude-mem/update.sh'"
# enabled = true
# timeout = 120
"""


def get_config_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        base = Path(xdg_config_home)
    else:
        base = Path.home() / ".config"
    return base / "claude-updater" / "config.toml"


def load_config() -> dict:
    config_path = get_config_path()
    if not config_path.exists():
        return tomllib.loads(DEFAULT_CONFIG)
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def init_config() -> Path:
    config_path = get_config_path()
    if config_path.exists():
        raise FileExistsError(f"Config file already exists: {config_path}")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(DEFAULT_CONFIG)
    return config_path


def get_adapter_config(config: dict, adapter_key: str) -> dict:
    adapter_cfg = config.get("adapters", {}).get(adapter_key, {})
    if not adapter_cfg:
        return {}
    result = dict(adapter_cfg)
    if "plugin_dir" in result:
        result["plugin_dir"] = str(Path(result["plugin_dir"]).expanduser())
    return result
