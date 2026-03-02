"""Tests for tool adapters with mocked subprocess."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from claude_updater.adapters.base import ToolAdapter, VersionInfo
from claude_updater.adapters.claude_code import ClaudeCodeAdapter
from claude_updater.adapters.beads_cli import BeadsCliAdapter
from claude_updater.adapters.dolt import DoltAdapter


class TestClaudeCodeAdapter:
    def test_get_installed_version(self):
        adapter = ClaudeCodeAdapter()
        with patch("subprocess.run") as mock:
            mock.return_value = MagicMock(
                stdout="2.1.63 (Claude Code)\n", returncode=0
            )
            assert adapter.get_installed_version() == "2.1.63"

    def test_get_latest_version(self):
        adapter = ClaudeCodeAdapter()
        with patch("subprocess.run") as mock:
            mock.return_value = MagicMock(
                stdout="v2.2.0\n", returncode=0
            )
            assert adapter.get_latest_version() == "2.2.0"

    def test_get_latest_version_strips_v(self):
        adapter = ClaudeCodeAdapter()
        with patch("subprocess.run") as mock:
            mock.return_value = MagicMock(stdout="v2.2.0\n", returncode=0)
            assert adapter.get_latest_version() == "2.2.0"

    def test_apply_update_returns_false(self):
        adapter = ClaudeCodeAdapter()
        assert adapter.apply_update() is False

    def test_properties(self):
        adapter = ClaudeCodeAdapter()
        assert adapter.name == "Claude Code"
        assert adapter.key == "claude_code"
        assert adapter.update_command == "auto-update (restart Claude Code)"

    def test_check_status_no_update(self):
        adapter = ClaudeCodeAdapter()
        with patch("subprocess.run") as mock:
            def side_effect(cmd, **kwargs):
                if cmd[0] == "claude":
                    return MagicMock(stdout="2.1.63 (Claude Code)\n", returncode=0)
                elif cmd[0] == "gh":
                    return MagicMock(stdout="v2.1.63\n", returncode=0)
                return MagicMock(stdout="", returncode=1)
            mock.side_effect = side_effect
            info = adapter.check_status()
            assert not info.has_update
            assert info.installed_version == "2.1.63"

    def test_check_status_with_update(self):
        adapter = ClaudeCodeAdapter()
        with patch("subprocess.run") as mock:
            def side_effect(cmd, **kwargs):
                if cmd[0] == "claude":
                    return MagicMock(stdout="2.1.63 (Claude Code)\n", returncode=0)
                elif cmd[0] == "gh":
                    return MagicMock(stdout="v2.2.0\n", returncode=0)
                return MagicMock(stdout="", returncode=1)
            mock.side_effect = side_effect
            info = adapter.check_status()
            assert info.has_update
            assert info.update_method == "auto-update (restart Claude Code)"


class TestBeadsCliAdapter:
    def test_get_installed_version(self):
        adapter = BeadsCliAdapter()
        with patch("subprocess.run") as mock:
            mock.return_value = MagicMock(
                stdout="beads 0.55.4\n", returncode=0
            )
            assert adapter.get_installed_version() == "0.55.4"

    def test_get_latest_version(self):
        adapter = BeadsCliAdapter()
        brew_json = json.dumps({"formulae": [{"versions": {"stable": "0.56.0"}}]})
        with patch("subprocess.run") as mock:
            mock.return_value = MagicMock(stdout=brew_json, returncode=0)
            assert adapter.get_latest_version() == "0.56.0"

    def test_apply_update(self):
        adapter = BeadsCliAdapter()
        with patch("subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0)
            assert adapter.apply_update() is True

    def test_properties(self):
        adapter = BeadsCliAdapter()
        assert adapter.name == "beads CLI"
        assert adapter.key == "beads_cli"
        assert adapter.update_command == "brew upgrade beads"


class TestDoltAdapter:
    def test_get_installed_version(self):
        adapter = DoltAdapter()
        with patch("subprocess.run") as mock:
            mock.return_value = MagicMock(
                stdout="dolt 1.82.6\n", returncode=0
            )
            assert adapter.get_installed_version() == "1.82.6"

    def test_get_latest_version(self):
        adapter = DoltAdapter()
        brew_json = json.dumps({"formulae": [{"versions": {"stable": "1.83.0"}}]})
        with patch("subprocess.run") as mock:
            mock.return_value = MagicMock(stdout=brew_json, returncode=0)
            assert adapter.get_latest_version() == "1.83.0"

    def test_changelog_delta(self):
        adapter = DoltAdapter()
        releases = json.dumps([
            {"tagName": "v1.83.0", "body": "New features"},
            {"tagName": "v1.82.6", "body": "Bug fixes"},
        ])
        with patch("subprocess.run") as mock:
            mock.return_value = MagicMock(stdout=releases, returncode=0)
            delta = adapter.get_changelog_delta("1.82.6", "1.83.0")
            assert "v1.83.0" in delta

    def test_properties(self):
        adapter = DoltAdapter()
        assert adapter.name == "dolt"
        assert adapter.key == "dolt"
        assert adapter.update_command == "brew upgrade dolt"


class TestToolAdapterBase:
    def test_configure(self):
        adapter = ClaudeCodeAdapter()
        adapter.configure({"foo": "bar"})
        assert adapter._settings == {"foo": "bar"}

    def test_version_info_dataclass(self):
        info = VersionInfo(
            tool_name="Test",
            key="test",
            installed_version="1.0",
            latest_version="2.0",
            has_update=True,
            update_method="pip install",
        )
        assert info.changelog_delta == ""
        assert info.has_update is True
