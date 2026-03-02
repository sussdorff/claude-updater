# claude-updater

Multi-tool update checker for the Claude Code ecosystem.

## Installation

```bash
# Via uv
uv tool install claude-updater

# Via pipx
pipx install claude-updater

# Via pip
pip install claude-updater
```

## Quick Start

```bash
# Check for updates
claude-updater check

# Check and apply updates interactively
claude-updater update

# Initialize config
claude-updater config init
```

## Built-in Adapters

| Adapter | Tool | Update Method |
|---------|------|---------------|
| `claude_code` | Claude Code | Auto-update (informational) |
| `claude_mem` | claude-mem plugin | `git pull` |
| `beads_cli` | beads CLI | `brew upgrade` |
| `beads_plugin` | beads plugin | `git pull` |
| `dolt` | dolt | `brew upgrade` |

## Configuration

Config file: `~/.config/claude-updater/config.toml`

```bash
# Create default config
claude-updater config init

# Show current config
claude-updater config show
```

### Config Options

```toml
[general]
cache_ttl = 86400          # 24h cache TTL in seconds
check_on_startup = true

[adapters.claude_code]
enabled = true

[adapters.claude_mem]
enabled = true
plugin_dir = "~/.claude/plugins/marketplaces/thedotmack"

[adapters.beads_cli]
enabled = true

[adapters.beads_plugin]
enabled = true
plugin_dir = "~/.claude/plugins/marketplaces/beads-marketplace"

[adapters.dolt]
enabled = true
```

## CLI Reference

```bash
claude-updater check              # Check all enabled adapters
claude-updater check --force      # Ignore cache
claude-updater check --json       # Machine-readable output
claude-updater update             # Interactive update
claude-updater update --yes       # Auto-approve updates
claude-updater config init        # Create default config
claude-updater config show        # Show current config
claude-updater list               # List available adapters
```

## Writing Custom Adapters

Create a new file in `src/claude_updater/adapters/`:

```python
from claude_updater.adapters.base import ToolAdapter

class MyToolAdapter(ToolAdapter):
    @property
    def name(self) -> str:
        return "My Tool"

    @property
    def key(self) -> str:
        return "my_tool"

    def get_installed_version(self) -> str:
        # Return currently installed version
        ...

    def get_latest_version(self) -> str:
        # Return latest available version
        ...

    def get_changelog_delta(self, from_ver: str, to_ver: str) -> str:
        # Return changelog text between versions
        ...

    def apply_update(self) -> bool:
        # Apply the update, return True on success
        ...
```

Then register it in `adapters/__init__.py`:

```python
ADAPTER_REGISTRY["my_tool"] = MyToolAdapter
```

## License

MIT
