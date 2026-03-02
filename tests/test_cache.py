"""Tests for the version cache."""

from __future__ import annotations

import json
import time

from claude_updater.cache import VersionCache


def test_cache_not_fresh_when_missing(tmp_cache):
    cache = VersionCache()
    assert not cache.is_fresh()


def test_cache_read_returns_empty_when_missing(tmp_cache):
    cache = VersionCache()
    assert cache.read() == {}


def test_cache_write_and_read(tmp_cache, sample_versions):
    cache = VersionCache()
    cache.write(sample_versions)
    data = cache.read()
    assert "versions" in data
    assert "last_check" in data
    assert data["versions"] == sample_versions


def test_cache_is_fresh_after_write(tmp_cache, sample_versions):
    cache = VersionCache()
    cache.write(sample_versions)
    assert cache.is_fresh()


def test_cache_expires_after_ttl(tmp_cache, sample_versions):
    cache = VersionCache(ttl=1)
    cache.write(sample_versions)

    # Manually set last_check to the past
    data = cache.read()
    data["last_check"] = int(time.time()) - 10
    with open(cache.cache_path, "w") as f:
        json.dump(data, f)

    assert not cache.is_fresh()


def test_cache_invalidate(tmp_cache, sample_versions):
    cache = VersionCache()
    cache.write(sample_versions)
    assert cache.cache_path.exists()
    cache.invalidate()
    assert not cache.cache_path.exists()
    assert cache.read() == {}


def test_cache_handles_corrupt_file(tmp_cache):
    cache = VersionCache()
    cache.cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache.cache_path.write_text("not valid json {{{")
    assert cache.read() == {}
    assert not cache.is_fresh()
