"""Tests for post-update hooks."""

from __future__ import annotations

from claude_updater.hooks import (
    HookConfig,
    get_hooks_for_adapter,
    load_hooks,
    run_post_update_hooks,
)


class TestLoadHooks:
    def test_empty_config(self):
        assert load_hooks({}) == []

    def test_no_hooks_section(self):
        assert load_hooks({"general": {"cache_ttl": 86400}}) == []

    def test_single_hook(self):
        config = {
            "hooks": {
                "post_update": [
                    {
                        "adapter": "claude_mem",
                        "command": "echo hello",
                        "enabled": True,
                        "timeout": 60,
                    }
                ]
            }
        }
        hooks = load_hooks(config)
        assert len(hooks) == 1
        assert hooks[0].adapter == "claude_mem"
        assert hooks[0].command == "echo hello"
        assert hooks[0].timeout == 60

    def test_wildcard_adapter(self):
        config = {
            "hooks": {
                "post_update": [{"adapter": "*", "command": "echo all"}]
            }
        }
        hooks = load_hooks(config)
        assert hooks[0].adapter == "*"

    def test_default_adapter_is_wildcard(self):
        config = {
            "hooks": {
                "post_update": [{"command": "echo default"}]
            }
        }
        hooks = load_hooks(config)
        assert hooks[0].adapter == "*"

    def test_disabled_hook(self):
        config = {
            "hooks": {
                "post_update": [
                    {"adapter": "claude_mem", "command": "echo off", "enabled": False}
                ]
            }
        }
        hooks = load_hooks(config)
        assert len(hooks) == 1
        assert not hooks[0].enabled

    def test_skip_empty_command(self):
        config = {
            "hooks": {
                "post_update": [{"adapter": "claude_mem", "command": ""}]
            }
        }
        assert load_hooks(config) == []

    def test_default_timeout(self):
        config = {
            "hooks": {
                "post_update": [{"adapter": "claude_mem", "command": "echo hi"}]
            }
        }
        hooks = load_hooks(config)
        assert hooks[0].timeout == 120

    def test_multiple_hooks(self):
        config = {
            "hooks": {
                "post_update": [
                    {"adapter": "claude_mem", "command": "echo a"},
                    {"adapter": "dolt", "command": "echo b"},
                    {"adapter": "*", "command": "echo c"},
                ]
            }
        }
        hooks = load_hooks(config)
        assert len(hooks) == 3


class TestGetHooksForAdapter:
    def test_exact_match(self):
        hooks = [
            HookConfig(adapter="claude_mem", command="echo a"),
            HookConfig(adapter="dolt", command="echo b"),
        ]
        result = get_hooks_for_adapter(hooks, "claude_mem")
        assert len(result) == 1
        assert result[0].command == "echo a"

    def test_wildcard_matches_any(self):
        hooks = [
            HookConfig(adapter="*", command="echo all"),
        ]
        result = get_hooks_for_adapter(hooks, "dolt")
        assert len(result) == 1

    def test_mixed_specific_and_wildcard(self):
        hooks = [
            HookConfig(adapter="claude_mem", command="echo specific"),
            HookConfig(adapter="*", command="echo all"),
        ]
        result = get_hooks_for_adapter(hooks, "claude_mem")
        assert len(result) == 2

    def test_disabled_hooks_excluded(self):
        hooks = [
            HookConfig(adapter="claude_mem", command="echo a", enabled=False),
            HookConfig(adapter="claude_mem", command="echo b", enabled=True),
        ]
        result = get_hooks_for_adapter(hooks, "claude_mem")
        assert len(result) == 1
        assert result[0].command == "echo b"

    def test_no_matching_hooks(self):
        hooks = [
            HookConfig(adapter="dolt", command="echo a"),
        ]
        result = get_hooks_for_adapter(hooks, "claude_mem")
        assert len(result) == 0


class TestRunPostUpdateHooks:
    def test_successful_hook(self, capsys):
        hooks = [HookConfig(adapter="claude_mem", command="echo done")]
        result = run_post_update_hooks(hooks, "claude_mem")
        assert result is True
        captured = capsys.readouterr()
        assert "done" in captured.out or "completed" in captured.out

    def test_no_matching_hooks_returns_true(self):
        hooks = [HookConfig(adapter="dolt", command="echo nope")]
        result = run_post_update_hooks(hooks, "claude_mem")
        assert result is True

    def test_failing_hook_returns_false(self, capsys):
        hooks = [HookConfig(adapter="claude_mem", command="exit 1")]
        result = run_post_update_hooks(hooks, "claude_mem")
        assert result is False

    def test_timeout_returns_false(self, capsys):
        hooks = [HookConfig(adapter="claude_mem", command="sleep 10", timeout=1)]
        result = run_post_update_hooks(hooks, "claude_mem")
        assert result is False
        captured = capsys.readouterr()
        assert "timed out" in captured.err

    def test_multiple_hooks_all_run(self, capsys):
        hooks = [
            HookConfig(adapter="claude_mem", command="echo first"),
            HookConfig(adapter="*", command="echo second"),
        ]
        result = run_post_update_hooks(hooks, "claude_mem")
        assert result is True

    def test_first_fails_second_still_runs(self, capsys):
        hooks = [
            HookConfig(adapter="claude_mem", command="exit 1"),
            HookConfig(adapter="*", command="echo ok"),
        ]
        result = run_post_update_hooks(hooks, "claude_mem")
        assert result is False  # overall fails
        captured = capsys.readouterr()
        assert "ok" in captured.out  # second hook still ran
