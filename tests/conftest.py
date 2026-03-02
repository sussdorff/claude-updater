"""Shared fixtures for claude-updater tests."""

from __future__ import annotations

import json
import time

import pytest


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Set up temporary config directory."""
    config_dir = tmp_path / "config" / "claude-updater"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return config_dir


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    """Set up temporary cache directory."""
    cache_dir = tmp_path / "cache" / "claude-updater"
    cache_dir.mkdir(parents=True)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return cache_dir


@pytest.fixture
def sample_versions():
    """Sample version data for cache tests."""
    return {
        "claude_code": {
            "tool_name": "Claude Code",
            "installed": "2.1.63",
            "latest": "2.2.0",
            "has_update": True,
            "update_method": "auto-update (restart Claude Code)",
        },
        "dolt": {
            "tool_name": "dolt",
            "installed": "1.82.6",
            "latest": "1.82.6",
            "has_update": False,
            "update_method": "",
        },
    }


@pytest.fixture
def mock_subprocess(monkeypatch):
    """Helper to mock subprocess.run calls."""
    results = {}

    class MockResult:
        def __init__(self, stdout="", stderr="", returncode=0):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    def mock_run(cmd, **kwargs):
        key = tuple(cmd) if isinstance(cmd, list) else cmd
        for pattern, result in results.items():
            if isinstance(pattern, tuple) and key[:len(pattern)] == pattern:
                return result
            elif isinstance(pattern, str) and pattern in str(key):
                return result
        return MockResult()

    import subprocess
    monkeypatch.setattr(subprocess, "run", mock_run)
    return results, MockResult
