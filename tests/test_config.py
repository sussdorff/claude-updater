"""Tests for config loading."""

from __future__ import annotations

from claude_updater.config import (
    DEFAULT_CONFIG,
    get_adapter_config,
    get_config_path,
    init_config,
    load_config,
)


def test_config_path_respects_xdg(tmp_config, monkeypatch):
    path = get_config_path()
    assert "claude-updater" in str(path)
    assert path.name == "config.toml"


def test_load_config_returns_defaults_when_missing(tmp_config):
    config = load_config()
    assert config["general"]["cache_ttl"] == 86400
    assert config["adapters"]["claude_code"]["enabled"] is True


def test_init_config_creates_file(tmp_config):
    path = init_config()
    assert path.exists()
    assert path.read_text() == DEFAULT_CONFIG


def test_init_config_raises_if_exists(tmp_config):
    init_config()
    import pytest
    with pytest.raises(FileExistsError):
        init_config()


def test_load_config_reads_file(tmp_config):
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("""
[general]
cache_ttl = 3600

[adapters.claude_code]
enabled = false
""")
    config = load_config()
    assert config["general"]["cache_ttl"] == 3600
    assert config["adapters"]["claude_code"]["enabled"] is False


def test_get_adapter_config_returns_empty_for_missing(tmp_config):
    config = load_config()
    result = get_adapter_config(config, "nonexistent")
    assert result == {}


def test_get_adapter_config_expands_tilde(tmp_config):
    config = {
        "adapters": {
            "claude_mem": {
                "enabled": True,
                "plugin_dir": "~/some/path",
            }
        }
    }
    result = get_adapter_config(config, "claude_mem")
    assert "~" not in result["plugin_dir"]
