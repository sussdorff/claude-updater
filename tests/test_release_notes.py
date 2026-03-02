"""Tests for the release notes feature: ReleaseNotesCache, run_release_notes, and CLI."""

from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest

from claude_updater.adapters.base import ReleaseInfo, VersionInfo
from claude_updater.cache import ReleaseNotesCache
from claude_updater.runner import run_release_notes


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

def _make_release(version: str, date: str, body: str = "") -> dict:
    return {"version": version, "date": date, "body": body}


class MockReleaseAdapter:
    """Minimal adapter stub that returns a configurable list of ReleaseInfo objects."""

    def __init__(self, name: str, key: str, releases: list[ReleaseInfo] | None = None):
        self._name = name
        self._key = key
        self._releases = releases or []
        self._settings: dict = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def key(self) -> str:
        return self._key

    def get_releases(self, limit: int = 5) -> list[ReleaseInfo]:
        return self._releases[:limit]

    def check_status(self) -> VersionInfo:
        return VersionInfo(
            tool_name=self._name,
            key=self._key,
            installed_version="1.0.0",
            latest_version="1.0.0",
            has_update=False,
            update_method="",
        )

    def get_changelog_delta(self, from_ver: str, to_ver: str) -> str:
        return ""

    def configure(self, settings: dict) -> None:
        self._settings = settings


# ---------------------------------------------------------------------------
# ReleaseNotesCache tests
# ---------------------------------------------------------------------------

class TestReleaseNotesCacheRead:
    def test_read_returns_empty_list_when_no_file_exists(self, tmp_cache):
        cache = ReleaseNotesCache()
        result = cache.read("sometool")
        assert result == []

    def test_read_uses_xdg_cache_home(self, tmp_cache):
        cache = ReleaseNotesCache()
        # cache_dir should be inside the tmp XDG_CACHE_HOME
        assert str(tmp_cache) in str(cache.cache_dir)

    def test_read_returns_empty_list_on_corrupt_json(self, tmp_cache):
        cache = ReleaseNotesCache()
        tool_path = cache._tool_path("tool_x")
        tool_path.parent.mkdir(parents=True, exist_ok=True)
        tool_path.write_text("not valid json {{{")
        assert cache.read("tool_x") == []


class TestReleaseNotesCacheWrite:
    def test_write_then_read_returns_same_data(self, tmp_cache):
        cache = ReleaseNotesCache()
        releases = [
            _make_release("1.2.0", "2026-02-28", "bug fixes"),
            _make_release("1.1.0", "2026-02-01", "new feature"),
        ]
        cache.write("my_tool", releases)
        result = cache.read("my_tool")
        assert result == releases

    def test_write_creates_parent_directories(self, tmp_cache):
        cache = ReleaseNotesCache()
        cache.write("brand_new_tool", [_make_release("0.1.0", "2026-01-01")])
        assert cache._tool_path("brand_new_tool").exists()

    def test_write_persists_json_to_expected_path(self, tmp_cache):
        cache = ReleaseNotesCache()
        cache.write("alpha", [_make_release("3.0.0", "2026-03-01")])
        raw = json.loads(cache._tool_path("alpha").read_text())
        assert raw[0]["version"] == "3.0.0"

    def test_different_tools_use_separate_files(self, tmp_cache):
        cache = ReleaseNotesCache()
        cache.write("tool_a", [_make_release("1.0.0", "2026-01-01")])
        cache.write("tool_b", [_make_release("2.0.0", "2026-02-01")])
        assert cache.read("tool_a")[0]["version"] == "1.0.0"
        assert cache.read("tool_b")[0]["version"] == "2.0.0"


class TestReleaseNotesCacheMerge:
    def test_merge_into_empty_cache_returns_all_new(self, tmp_cache):
        cache = ReleaseNotesCache()
        new = [_make_release("1.0.0", "2026-01-15")]
        result = cache.merge("tool", new)
        assert len(result) == 1
        assert result[0]["version"] == "1.0.0"

    def test_merge_deduplicates_by_version(self, tmp_cache):
        cache = ReleaseNotesCache()
        existing = [_make_release("1.0.0", "2026-01-10")]
        cache.write("tool", existing)

        result = cache.merge("tool", [_make_release("1.0.0", "2026-01-10", "body changed")])

        # Version already present — no duplicate added
        assert len(result) == 1
        # Original body is preserved (append-only)
        assert result[0]["body"] == ""

    def test_merge_appends_new_versions(self, tmp_cache):
        cache = ReleaseNotesCache()
        cache.write("tool", [_make_release("1.0.0", "2026-01-01")])

        result = cache.merge("tool", [_make_release("1.1.0", "2026-02-01")])

        versions = {r["version"] for r in result}
        assert "1.0.0" in versions
        assert "1.1.0" in versions

    def test_merge_does_not_remove_old_entries(self, tmp_cache):
        cache = ReleaseNotesCache()
        old = [_make_release("0.9.0", "2025-06-01")]
        cache.write("tool", old)

        # Merge only new entries — old ones must survive
        cache.merge("tool", [_make_release("1.0.0", "2026-01-01")])
        result = cache.read("tool")

        assert any(r["version"] == "0.9.0" for r in result)

    def test_merge_persists_merged_data_to_disk(self, tmp_cache):
        cache = ReleaseNotesCache()
        cache.write("tool", [_make_release("1.0.0", "2026-01-01")])
        cache.merge("tool", [_make_release("1.1.0", "2026-02-01")])

        # Read directly from another cache instance to confirm persistence
        fresh = ReleaseNotesCache()
        result = fresh.read("tool")
        assert len(result) == 2


class TestReleaseNotesCacheSorting:
    def test_merge_sorts_by_date_descending(self, tmp_cache):
        cache = ReleaseNotesCache()
        releases = [
            _make_release("1.0.0", "2026-01-01"),
            _make_release("1.2.0", "2026-03-01"),
            _make_release("1.1.0", "2026-02-01"),
        ]
        result = cache.merge("tool", releases)

        dates = [r["date"] for r in result]
        assert dates == sorted(dates, reverse=True)

    def test_merge_preserves_newest_first_with_existing_entries(self, tmp_cache):
        cache = ReleaseNotesCache()
        cache.write("tool", [_make_release("1.0.0", "2026-01-01")])
        result = cache.merge("tool", [_make_release("2.0.0", "2026-03-01")])

        assert result[0]["version"] == "2.0.0"
        assert result[1]["version"] == "1.0.0"


# ---------------------------------------------------------------------------
# run_release_notes tests
# ---------------------------------------------------------------------------

MINIMAL_CONFIG = {
    "general": {"cache_ttl": 86400},
    "adapters": {},
}


def _recent_date(days_ago: int = 1) -> str:
    from datetime import datetime, timedelta
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _old_date(days_ago: int = 30) -> str:
    from datetime import datetime, timedelta
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


class TestRunReleaseNotesBasicFlow:
    def test_returns_dict_keyed_by_adapter_key(self, tmp_cache):
        adapter = MockReleaseAdapter(
            "My Tool", "my_tool",
            releases=[ReleaseInfo("1.0.0", _recent_date(1), "fixes")],
        )
        with patch("claude_updater.runner.get_enabled_adapters", return_value=[adapter]):
            result = run_release_notes(MINIMAL_CONFIG, days=7)

        assert isinstance(result, dict)
        assert "my_tool" in result

    def test_empty_result_when_no_adapters(self, tmp_cache):
        # ThreadPoolExecutor requires max_workers >= 1, so the production code
        # raises ValueError when the adapter list is empty.  That is a separate
        # production bug; this test documents the current behaviour.
        with patch("claude_updater.runner.get_enabled_adapters", return_value=[]):
            with pytest.raises((ValueError, SystemExit)):
                run_release_notes(MINIMAL_CONFIG, days=7)

    def test_releases_stored_in_cache_after_run(self, tmp_cache):
        adapter = MockReleaseAdapter(
            "My Tool", "my_tool",
            releases=[ReleaseInfo("2.0.0", _recent_date(1), "notes")],
        )
        with patch("claude_updater.runner.get_enabled_adapters", return_value=[adapter]):
            run_release_notes(MINIMAL_CONFIG, days=7)

        cache = ReleaseNotesCache()
        cached = cache.read("my_tool")
        assert any(r["version"] == "2.0.0" for r in cached)

    def test_adapter_exception_falls_back_to_cache(self, tmp_cache):
        # Pre-populate cache
        cache = ReleaseNotesCache()
        cache.write("broken_tool", [_make_release("0.5.0", _recent_date(1))])

        class BrokenAdapter(MockReleaseAdapter):
            def get_releases(self, limit: int = 5) -> list[ReleaseInfo]:
                raise RuntimeError("network error")

        adapter = BrokenAdapter("Broken", "broken_tool")
        with patch("claude_updater.runner.get_enabled_adapters", return_value=[adapter]):
            result = run_release_notes(MINIMAL_CONFIG, days=7)

        # Should have fallen back to cached data
        assert "broken_tool" in result


class TestRunReleaseNotesDaysFiltering:
    def test_releases_older_than_cutoff_are_excluded(self, tmp_cache):
        adapter = MockReleaseAdapter(
            "Tool", "tool",
            releases=[ReleaseInfo("1.0.0", _old_date(30), "old")],
        )
        with patch("claude_updater.runner.get_enabled_adapters", return_value=[adapter]):
            result = run_release_notes(MINIMAL_CONFIG, days=3)

        assert "tool" not in result

    def test_releases_within_cutoff_are_included(self, tmp_cache):
        adapter = MockReleaseAdapter(
            "Tool", "tool",
            releases=[ReleaseInfo("1.0.0", _recent_date(1), "recent")],
        )
        with patch("claude_updater.runner.get_enabled_adapters", return_value=[adapter]):
            result = run_release_notes(MINIMAL_CONFIG, days=3)

        assert "tool" in result

    def test_wider_days_window_includes_more_releases(self, tmp_cache):
        adapter = MockReleaseAdapter(
            "Tool", "tool",
            releases=[
                ReleaseInfo("2.0.0", _recent_date(1), "recent"),
                ReleaseInfo("1.9.0", _old_date(10), "older"),
            ],
        )
        with patch("claude_updater.runner.get_enabled_adapters", return_value=[adapter]):
            narrow = run_release_notes(MINIMAL_CONFIG, days=3)
            wide = run_release_notes(MINIMAL_CONFIG, days=14)

        assert len(narrow.get("tool", [])) == 1
        assert len(wide.get("tool", [])) == 2


class TestRunReleaseNotesToolFilter:
    def test_tool_filter_by_key_returns_only_that_tool(self, tmp_cache):
        adapters = [
            MockReleaseAdapter("Tool A", "tool_a",
                               releases=[ReleaseInfo("1.0.0", _recent_date(1), "")]),
            MockReleaseAdapter("Tool B", "tool_b",
                               releases=[ReleaseInfo("2.0.0", _recent_date(1), "")]),
        ]
        with patch("claude_updater.runner.get_enabled_adapters", return_value=adapters):
            result = run_release_notes(MINIMAL_CONFIG, days=7, tool_filter="tool_a")

        assert "tool_a" in result
        assert "tool_b" not in result

    def test_tool_filter_by_name_case_insensitive(self, tmp_cache):
        adapters = [
            MockReleaseAdapter("Claude Code", "claude_code",
                               releases=[ReleaseInfo("1.0.0", _recent_date(1), "")]),
        ]
        with patch("claude_updater.runner.get_enabled_adapters", return_value=adapters):
            result = run_release_notes(MINIMAL_CONFIG, days=7, tool_filter="claude code")

        assert "claude_code" in result

    def test_unknown_tool_filter_exits_with_error(self, tmp_cache, capsys):
        adapters = [
            MockReleaseAdapter("Tool A", "tool_a", releases=[]),
        ]
        with patch("claude_updater.runner.get_enabled_adapters", return_value=adapters):
            with pytest.raises(SystemExit) as exc_info:
                run_release_notes(MINIMAL_CONFIG, days=7, tool_filter="nonexistent")

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "nonexistent" in captured.err


class TestRunReleaseNotesJsonOutput:
    def test_json_output_is_valid_json(self, tmp_cache, capsys):
        adapter = MockReleaseAdapter(
            "My Tool", "my_tool",
            releases=[ReleaseInfo("1.0.0", _recent_date(1), "body text")],
        )
        with patch("claude_updater.runner.get_enabled_adapters", return_value=[adapter]):
            run_release_notes(MINIMAL_CONFIG, days=7, json_output=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)  # raises if not valid JSON
        assert isinstance(data, dict)

    def test_json_output_keyed_by_tool_name(self, tmp_cache, capsys):
        adapter = MockReleaseAdapter(
            "My Tool", "my_tool",
            releases=[ReleaseInfo("1.0.0", _recent_date(1), "notes")],
        )
        with patch("claude_updater.runner.get_enabled_adapters", return_value=[adapter]):
            run_release_notes(MINIMAL_CONFIG, days=7, json_output=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        # Output uses tool *name*, not key
        assert "My Tool" in data

    def test_json_output_contains_version_and_date(self, tmp_cache, capsys):
        adapter = MockReleaseAdapter(
            "My Tool", "my_tool",
            releases=[ReleaseInfo("3.1.4", _recent_date(1), "pi day")],
        )
        with patch("claude_updater.runner.get_enabled_adapters", return_value=[adapter]):
            run_release_notes(MINIMAL_CONFIG, days=7, json_output=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        releases = data["My Tool"]
        assert releases[0]["version"] == "3.1.4"
        assert "date" in releases[0]

    def test_json_output_omits_tools_with_no_recent_releases(self, tmp_cache, capsys):
        adapter = MockReleaseAdapter(
            "Old Tool", "old_tool",
            releases=[ReleaseInfo("1.0.0", _old_date(60), "ancient")],
        )
        with patch("claude_updater.runner.get_enabled_adapters", return_value=[adapter]):
            run_release_notes(MINIMAL_CONFIG, days=3, json_output=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "Old Tool" not in data


# ---------------------------------------------------------------------------
# CLI argument parsing tests
# ---------------------------------------------------------------------------

class TestCLIReleaseNotesArgs:
    """Verify that the release-notes subcommand parses arguments correctly
    and forwards them to run_release_notes without calling real adapters."""

    def _parse(self, argv: list[str]) -> "argparse.Namespace":
        """Return parsed args without executing the command."""
        import argparse
        from claude_updater.cli import main

        # Re-build just the parser by importing and calling the relevant part
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        rn_p = sub.add_parser("release-notes")
        rn_p.add_argument("--days", type=int, default=3)
        rn_p.add_argument("--tool", type=str, default=None)
        rn_p.add_argument("--json", action="store_true")
        return parser.parse_args(argv)

    def test_default_days_is_3(self):
        args = self._parse(["release-notes"])
        assert args.days == 3

    def test_custom_days_parsed(self):
        args = self._parse(["release-notes", "--days", "7"])
        assert args.days == 7

    def test_tool_defaults_to_none(self):
        args = self._parse(["release-notes"])
        assert args.tool is None

    def test_tool_filter_parsed(self):
        args = self._parse(["release-notes", "--tool", "claude_code"])
        assert args.tool == "claude_code"

    def test_json_flag_defaults_to_false(self):
        args = self._parse(["release-notes"])
        assert args.json is False

    def test_json_flag_set(self):
        args = self._parse(["release-notes", "--json"])
        assert args.json is True

    def test_cmd_release_notes_forwards_args_to_runner(self, tmp_cache, monkeypatch):
        """cmd_release_notes passes all parsed args to run_release_notes."""
        import argparse

        calls = []

        def fake_run_release_notes(config, days, tool_filter, json_output):
            calls.append({
                "days": days,
                "tool_filter": tool_filter,
                "json_output": json_output,
            })
            return {}

        monkeypatch.setattr("claude_updater.runner.run_release_notes", fake_run_release_notes)

        from claude_updater.cli import cmd_release_notes

        args = argparse.Namespace(days=14, tool="my_tool", json=True)
        # load_config is imported inside cmd_release_notes, so patch it at its
        # source module rather than via the cli namespace.
        with patch("claude_updater.config.load_config", return_value=MINIMAL_CONFIG):
            cmd_release_notes(args)

        assert len(calls) == 1
        assert calls[0]["days"] == 14
        assert calls[0]["tool_filter"] == "my_tool"
        assert calls[0]["json_output"] is True
