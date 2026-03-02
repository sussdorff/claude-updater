"""Tests for tool adapters with mocked subprocess."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from claude_updater.adapters.base import ToolAdapter, VersionInfo, _extract_changelog_section
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
        brew_json = json.dumps({"formulae": [{"linked_keg": "0.55.4", "versions": {"stable": "0.57.0"}}]})
        with patch("subprocess.run") as mock:
            mock.return_value = MagicMock(stdout=brew_json, returncode=0)
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
        brew_json = json.dumps({"formulae": [{"linked_keg": "1.82.6", "versions": {"stable": "1.83.0"}}]})
        with patch("subprocess.run") as mock:
            mock.return_value = MagicMock(stdout=brew_json, returncode=0)
            assert adapter.get_installed_version() == "1.82.6"

    def test_get_latest_version(self):
        adapter = DoltAdapter()
        brew_json = json.dumps({"formulae": [{"versions": {"stable": "1.83.0"}}]})
        with patch("subprocess.run") as mock:
            mock.return_value = MagicMock(stdout=brew_json, returncode=0)
            assert adapter.get_latest_version() == "1.83.0"

    def test_changelog_delta(self):
        adapter = DoltAdapter()
        with patch("subprocess.run") as mock:
            def side_effect(cmd, **kwargs):
                cmd_str = " ".join(cmd)
                if "releases" in cmd_str and "--paginate" in cmd_str:
                    return MagicMock(stdout="v1.83.0\nv1.82.6\n", returncode=0)
                if "releases/tags" in cmd_str:
                    return MagicMock(stdout="## Changelog\n* New features\n* Bug fixes\n", returncode=0)
                return MagicMock(stdout="", returncode=1)
            mock.side_effect = side_effect
            delta = adapter.get_changelog_delta("1.82.6", "1.83.0")
            assert "v1.83.0" in delta

    def test_properties(self):
        adapter = DoltAdapter()
        assert adapter.name == "dolt"
        assert adapter.key == "dolt"
        assert adapter.update_command == "brew upgrade dolt"


class TestExtractChangelogSection:
    def test_dolt_style_captures_intro_and_dolt_prs_only(self):
        body = (
            "This is a minor version bump.\n"
            "\n"
            "# Merged PRs\n"
            "\n"
            "## dolt\n"
            "\n"
            "* [123](https://github.com/dolthub/dolt/pull/123): Fix bug\n"
            "* [124](https://github.com/dolthub/dolt/pull/124): Add feature\n"
            "\n"
            "## go-mysql-server\n"
            "\n"
            "* [456](https://github.com/dolthub/go-mysql-server/pull/456): GMS change\n"
            "\n"
            "# Closed Issues\n"
            "\n"
            "* [789](https://github.com/dolthub/dolt/issues/789): Some issue\n"
        )
        result = _extract_changelog_section(body)
        assert "minor version bump" in result
        assert "Fix bug" in result
        assert "Add feature" in result
        assert "GMS change" not in result
        assert "Closed Issues" not in result
        assert "Some issue" not in result

    def test_dolt_style_without_dolt_subsection(self):
        body = (
            "Intro text here.\n"
            "\n"
            "# Merged PRs\n"
            "\n"
            "* [100](https://example.com/100): Direct PR\n"
            "\n"
            "# Closed Issues\n"
        )
        result = _extract_changelog_section(body)
        assert "Intro text here" in result
        # No ## dolt section, so no PR entries captured via dolt path
        # but intro is still there

    def test_standard_changelog_section(self):
        body = (
            "# Release 1.0\n"
            "\n"
            "## Changelog\n"
            "\n"
            "* Fixed login bug\n"
            "* Added dark mode\n"
            "\n"
            "## Install\n"
            "\n"
            "Download from...\n"
        )
        result = _extract_changelog_section(body)
        assert "Fixed login bug" in result
        assert "Added dark mode" in result
        assert "Download from" not in result

    def test_fallback_to_bullet_points(self):
        body = (
            "Some release\n"
            "\n"
            "* Change one\n"
            "* Change two\n"
        )
        result = _extract_changelog_section(body)
        assert "Change one" in result
        assert "Change two" in result

    def test_strips_html_and_dependabot_noise(self):
        body = (
            "# Merged PRs\n"
            "\n"
            "## dolt\n"
            "\n"
            "* [10](https://example.com/10): Bump foo from 1.0 to 1.1\n"
            "  Bumps [foo](https://example.com) from 1.0 to 1.1.\n"
            "  <details>\n"
            "  <summary>Commits</summary>\n"
            "  <ul>\n"
            "  <li>some commit</li>\n"
            "  </ul>\n"
            "  </details>\n"
            "  <br />\n"
            "  [![Badge](https://example.com/badge)]\n"
            "  Dependabot will resolve any conflicts.\n"
            "  [//]: # (dependabot-automerge-start)\n"
            "  [//]: # (dependabot-automerge-end)\n"
            "  ---\n"
            "  - `@dependabot rebase` will rebase this PR\n"
            "  - `@dependabot recreate` will recreate this PR\n"
            "  - `@dependabot ignore this dependency`\n"
            "* [20](https://example.com/20): Real change\n"
        )
        result = _extract_changelog_section(body)
        assert "Bump foo" in result
        assert "<details>" not in result
        assert "@dependabot" not in result
        assert "Badge" not in result
        assert "Real change" in result

    def test_strips_code_blocks(self):
        body = (
            "# Merged PRs\n"
            "\n"
            "## dolt\n"
            "\n"
            "* [10](https://example.com/10): Optimize function\n"
            "  This optimizes the function.\n"
            "  ```\n"
            "  BenchmarkOld    100    500 ns/op\n"
            "  ```\n"
            "  ```\n"
            "  BenchmarkNew    200    250 ns/op\n"
            "  ```\n"
            "* [20](https://example.com/20): Another PR\n"
        )
        result = _extract_changelog_section(body)
        assert "Optimize function" in result
        assert "BenchmarkOld" not in result
        assert "BenchmarkNew" not in result
        assert "Another PR" in result

    def test_condenses_pr_descriptions(self):
        body = (
            "# Merged PRs\n"
            "\n"
            "## dolt\n"
            "\n"
            "* [10](https://example.com/10): Add feature X\n"
            "  First line of description.\n"
            "  Second line should be dropped.\n"
            "  Third line should be dropped.\n"
            "* [20](https://example.com/20): Fix bug Y\n"
        )
        result = _extract_changelog_section(body)
        assert "Add feature X" in result
        assert "First line of description" in result
        assert "Second line" not in result
        assert "Third line" not in result
        assert "Fix bug Y" in result

    def test_truncation_at_30_lines(self):
        lines = ["Intro.\n", "\n", "# Merged PRs\n", "\n", "## dolt\n"]
        for i in range(40):
            lines.append(f"* [{i}](https://example.com/{i}): PR {i}\n")
        lines.append("\n## go-mysql-server\n")
        body = "".join(lines)
        result = _extract_changelog_section(body)
        assert "..." in result


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
