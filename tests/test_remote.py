"""Tests for remote version checking and updating."""

from __future__ import annotations

from unittest.mock import patch

from claude_updater.remote import (
    RemoteConfig,
    RemoteResult,
    _extract_version_json,
    _extract_version_regex,
    load_remote_configs,
    run_remote_check,
    run_remote_update,
)


class TestLoadRemoteConfigs:
    def test_empty_config(self):
        assert load_remote_configs({}) == {}

    def test_no_adapters(self):
        assert load_remote_configs({"general": {}}) == {}

    def test_no_remote_section(self):
        config = {"adapters": {"dolt": {"enabled": True}}}
        assert load_remote_configs(config) == {}

    def test_single_remote(self):
        config = {
            "adapters": {
                "dolt": {
                    "enabled": True,
                    "remote": {
                        "command": "ssh elysium 'pct exec 116 -- /usr/local/bin/dolt-update.sh'",
                    },
                }
            }
        }
        configs = load_remote_configs(config)
        assert "dolt" in configs
        assert "dolt-update.sh" in configs["dolt"].command
        assert configs["dolt"].parse_mode == "regex"
        assert configs["dolt"].timeout == 30
        assert configs["dolt"].update_timeout == 120

    def test_multiple_remotes(self):
        config = {
            "adapters": {
                "dolt": {
                    "remote": {"command": "ssh elysium 'dolt-update.sh'"},
                },
                "claude_mem": {
                    "remote": {
                        "command": "ssh elysium 'update.sh'",
                        "parse_mode": "json",
                    },
                },
            }
        }
        configs = load_remote_configs(config)
        assert len(configs) == 2
        assert configs["claude_mem"].parse_mode == "json"

    def test_disabled_remote(self):
        config = {
            "adapters": {
                "dolt": {
                    "remote": {
                        "command": "ssh elysium 'dolt-update.sh'",
                        "enabled": False,
                    },
                }
            }
        }
        assert load_remote_configs(config) == {}

    def test_empty_command_skipped(self):
        config = {
            "adapters": {
                "dolt": {
                    "remote": {"command": ""},
                }
            }
        }
        assert load_remote_configs(config) == {}

    def test_custom_version_regex(self):
        config = {
            "adapters": {
                "dolt": {
                    "remote": {
                        "command": "ssh elysium 'dolt-update.sh'",
                        "version_regex": r"v\d+\.\d+",
                    },
                }
            }
        }
        configs = load_remote_configs(config)
        assert configs["dolt"].version_regex == r"v\d+\.\d+"

    def test_custom_update_timeout(self):
        config = {
            "adapters": {
                "dolt": {
                    "remote": {
                        "command": "ssh elysium 'dolt-update.sh'",
                        "update_timeout": 300,
                    },
                }
            }
        }
        configs = load_remote_configs(config)
        assert configs["dolt"].update_timeout == 300


class TestExtractVersion:
    def test_regex_simple(self):
        assert _extract_version_regex("dolt version 1.82.6", r"\d+\.\d+\.\d+") == "1.82.6"

    def test_regex_with_prefix(self):
        assert _extract_version_regex("v2.3.4-beta", r"\d+\.\d+\.\d+") == "2.3.4"

    def test_regex_no_match(self):
        assert _extract_version_regex("no version here", r"\d+\.\d+\.\d+") == ""

    def test_regex_multiline(self):
        stdout = "some header\nversion: 3.14.159\nother stuff"
        assert _extract_version_regex(stdout, r"\d+\.\d+\.\d+") == "3.14.159"

    def test_json_extraction(self):
        assert _extract_version_json('{"version": "1.5.0", "name": "test"}') == "1.5.0"

    def test_json_invalid(self):
        assert _extract_version_json("not json") == ""

    def test_json_missing_key(self):
        assert _extract_version_json('{"name": "test"}') == ""

    def test_json_numeric_version(self):
        assert _extract_version_json('{"version": 2}') == "2"


class TestRunRemoteCheck:
    @patch("claude_updater.remote.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "dolt version 1.82.6\n"
        mock_run.return_value.stderr = ""

        rc = RemoteConfig(adapter_key="dolt", command="echo test")
        result = run_remote_check(rc)
        assert result.remote_version == "1.82.6"
        assert result.error == ""
        # Should call command with --version appended
        mock_run.assert_called_once()
        assert "--version" in mock_run.call_args[0][0]

    @patch("claude_updater.remote.subprocess.run")
    def test_json_mode(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '{"version": "1.5.0"}\n'
        mock_run.return_value.stderr = ""

        rc = RemoteConfig(adapter_key="claude_mem", command="echo test", parse_mode="json")
        result = run_remote_check(rc)
        assert result.remote_version == "1.5.0"

    @patch("claude_updater.remote.subprocess.run")
    def test_command_failure(self, mock_run):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = "ssh: connect to host elysium: Connection refused\n"

        rc = RemoteConfig(adapter_key="dolt", command="ssh elysium 'dolt-update.sh'")
        result = run_remote_check(rc)
        assert result.remote_version == ""
        assert "Connection refused" in result.error

    @patch("claude_updater.remote.subprocess.run")
    def test_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=30)

        rc = RemoteConfig(adapter_key="dolt", command="ssh elysium 'dolt-update.sh'")
        result = run_remote_check(rc)
        assert result.remote_version == ""
        assert "timeout" in result.error

    @patch("claude_updater.remote.subprocess.run")
    def test_command_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("No such file or directory")

        rc = RemoteConfig(adapter_key="dolt", command="/nonexistent")
        result = run_remote_check(rc)
        assert result.remote_version == ""
        assert "No such file" in result.error

    @patch("claude_updater.remote.subprocess.run")
    def test_no_version_in_output(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "no version info here\n"
        mock_run.return_value.stderr = ""

        rc = RemoteConfig(adapter_key="dolt", command="echo test")
        result = run_remote_check(rc)
        assert result.remote_version == ""
        assert "no version found" in result.error

    @patch("claude_updater.remote.subprocess.run")
    def test_exit_code_with_empty_stderr(self, mock_run):
        mock_run.return_value.returncode = 127
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""

        rc = RemoteConfig(adapter_key="dolt", command="missing_cmd")
        result = run_remote_check(rc)
        assert "exit 127" in result.error


class TestRunRemoteUpdate:
    @patch("claude_updater.remote.subprocess.run")
    def test_success(self, mock_run, capsys):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "✓ Updated to 1.83.0, service running\n"
        mock_run.return_value.stderr = ""

        rc = RemoteConfig(adapter_key="dolt", command="ssh elysium 'dolt-update.sh'")
        result = run_remote_update(rc, "dolt")
        assert result.remote_version == "1.83.0"
        assert result.error == ""
        # Should call command WITHOUT --version
        assert "--version" not in mock_run.call_args[0][0]

    @patch("claude_updater.remote.subprocess.run")
    def test_failure(self, mock_run, capsys):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = "Service failed to start\n"

        rc = RemoteConfig(adapter_key="dolt", command="ssh elysium 'dolt-update.sh'")
        result = run_remote_update(rc, "dolt")
        assert result.remote_version == ""
        assert "Service failed" in result.error
        captured = capsys.readouterr()
        assert "failed" in captured.err.lower()

    @patch("claude_updater.remote.subprocess.run")
    def test_timeout(self, mock_run, capsys):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=120)

        rc = RemoteConfig(adapter_key="dolt", command="ssh elysium 'dolt-update.sh'", update_timeout=120)
        result = run_remote_update(rc, "dolt")
        assert result.error == "timeout after 120s"
        captured = capsys.readouterr()
        assert "timeout" in captured.err

    @patch("claude_updater.remote.subprocess.run")
    def test_uses_update_timeout(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "version 1.0.0\n"
        mock_run.return_value.stderr = ""

        rc = RemoteConfig(adapter_key="dolt", command="echo test", update_timeout=300)
        run_remote_update(rc, "dolt")
        assert mock_run.call_args.kwargs["timeout"] == 300
