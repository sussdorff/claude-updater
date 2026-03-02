"""Tests for the runner/orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from claude_updater.adapters.base import VersionInfo
from claude_updater.runner import _check_adapter, run_check


class MockAdapter:
    def __init__(self, name, key, installed, latest):
        self._name = name
        self._key = key
        self._installed = installed
        self._latest = latest
        self._settings = {}

    @property
    def name(self):
        return self._name

    @property
    def key(self):
        return self._key

    @property
    def update_command(self):
        return "test-update"

    def check_status(self):
        has_update = self._installed != self._latest
        return VersionInfo(
            tool_name=self._name,
            key=self._key,
            installed_version=self._installed,
            latest_version=self._latest,
            has_update=has_update,
            update_method=self.update_command if has_update else "",
        )

    def configure(self, settings):
        self._settings = settings


def test_check_adapter_success():
    adapter = MockAdapter("Test", "test", "1.0", "2.0")
    result = _check_adapter(adapter)
    assert result.has_update
    assert result.installed_version == "1.0"
    assert result.latest_version == "2.0"


def test_check_adapter_exception():
    adapter = MagicMock()
    adapter.name = "Broken"
    adapter.key = "broken"
    adapter.check_status.side_effect = RuntimeError("fail")
    result = _check_adapter(adapter)
    assert result.installed_version == "error"
    assert not result.has_update


def test_run_check_with_mocked_adapters(tmp_cache, capsys):
    adapters = [
        MockAdapter("Tool A", "tool_a", "1.0", "1.0"),
        MockAdapter("Tool B", "tool_b", "1.0", "2.0"),
    ]

    config = {
        "general": {"cache_ttl": 86400},
        "adapters": {
            "tool_a": {"enabled": True},
            "tool_b": {"enabled": True},
        },
    }

    with patch("claude_updater.runner.get_enabled_adapters", return_value=adapters):
        results = run_check(config, force=True)

    assert len(results) == 2
    assert not results[0].has_update
    assert results[1].has_update


def test_run_check_json_output(tmp_cache, capsys):
    adapters = [
        MockAdapter("Tool A", "tool_a", "1.0", "2.0"),
    ]

    config = {
        "general": {"cache_ttl": 86400},
        "adapters": {"tool_a": {"enabled": True}},
    }

    with patch("claude_updater.runner.get_enabled_adapters", return_value=adapters):
        results = run_check(config, force=True, json_output=True)

    captured = capsys.readouterr()
    assert '"tool_a"' in captured.out
    assert '"has_update": true' in captured.out
