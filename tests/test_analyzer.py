"""Tests for AI changelog analyzer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from claude_updater.analyzer import analyze_changelogs, resolve_api_key


class TestResolveApiKey:
    def test_direct_key(self):
        config = {"api_key": "sk-test-123"}
        assert resolve_api_key(config) == "sk-test-123"

    def test_env_var(self, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "sk-env-456")
        config = {"api_key_env": "TEST_API_KEY"}
        assert resolve_api_key(config) == "sk-env-456"

    def test_env_var_missing(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
        config = {"api_key_env": "NONEXISTENT_KEY"}
        assert resolve_api_key(config) is None

    def test_cmd(self):
        config = {"api_key_cmd": "echo sk-cmd-789"}
        with patch("subprocess.run") as mock:
            mock.return_value = MagicMock(stdout="sk-cmd-789\n")
            assert resolve_api_key(config) == "sk-cmd-789"

    def test_priority_order(self):
        config = {
            "api_key": "direct",
            "api_key_env": "ENV_VAR",
            "api_key_cmd": "echo cmd",
        }
        assert resolve_api_key(config) == "direct"

    def test_empty_config(self):
        assert resolve_api_key({}) is None


class TestAnalyzeChangelogs:
    def test_no_api_key_returns_none(self, capsys):
        result = analyze_changelogs({"tool": "changelog"}, {})
        assert result is None

    def test_successful_analysis(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Analysis result"))]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("claude_updater.analyzer.resolve_api_key", return_value="sk-test"):
            with patch("openai.OpenAI", return_value=mock_client):
                result = analyze_changelogs(
                    {"Claude Code": "## v2.2.0\nNew features"},
                    {"api_base": "https://api.test.com", "model": "test-model"},
                )
                assert result == "Analysis result"

    def test_api_failure_returns_none(self, capsys):
        with patch("claude_updater.analyzer.resolve_api_key", return_value="sk-test"):
            with patch("openai.OpenAI", side_effect=Exception("API error")):
                result = analyze_changelogs(
                    {"tool": "changelog"},
                    {"api_base": "https://api.test.com", "model": "test-model"},
                )
                assert result is None
