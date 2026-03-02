"""Adapter registry and discovery."""

from __future__ import annotations

from claude_updater.adapters.beads_plugin import BeadsPluginAdapter
from claude_updater.adapters.claude_code import ClaudeCodeAdapter
from claude_updater.adapters.claude_mem import ClaudeMemAdapter
from claude_updater.adapters.dolt import DoltAdapter

ADAPTER_REGISTRY: dict[str, type] = {
    "claude_code": ClaudeCodeAdapter,
    "claude_mem": ClaudeMemAdapter,
    "beads_plugin": BeadsPluginAdapter,
    "dolt": DoltAdapter,
}


def get_enabled_adapters(config: dict) -> list:
    """Return instantiated adapters that are enabled in config."""
    adapters = []
    adapter_configs = config.get("adapters", {})
    for key, cls in ADAPTER_REGISTRY.items():
        adapter_cfg = adapter_configs.get(key, {})
        if adapter_cfg.get("enabled", True):
            adapter = cls()
            adapter.configure(adapter_cfg)
            adapters.append(adapter)
    return adapters
