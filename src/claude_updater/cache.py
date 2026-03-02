import json
import os
import time
from pathlib import Path


class VersionCache:
    def __init__(self, ttl: int = 86400):
        self.ttl = ttl

    @property
    def cache_path(self) -> Path:
        xdg = os.environ.get("XDG_CACHE_HOME")
        if xdg:
            base = Path(xdg)
        else:
            base = Path.home() / ".cache"
        return base / "claude-updater" / "versions.json"

    def is_fresh(self) -> bool:
        path = self.cache_path
        if not path.exists():
            return False
        data = self.read()
        last_check = data.get("last_check")
        if last_check is None:
            return False
        return (time.time() - last_check) < self.ttl

    def read(self) -> dict:
        path = self.cache_path
        if not path.exists():
            return {}
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def write(self, versions: dict) -> None:
        path = self.cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_check": int(time.time()),
            "versions": versions,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def invalidate(self) -> None:
        path = self.cache_path
        if path.exists():
            path.unlink()


class ReleaseNotesCache:
    """Append-only cache for release notes per tool."""

    @property
    def cache_dir(self) -> Path:
        xdg = os.environ.get("XDG_CACHE_HOME")
        if xdg:
            base = Path(xdg)
        else:
            base = Path.home() / ".cache"
        return base / "claude-updater" / "release-notes"

    def _tool_path(self, tool_key: str) -> Path:
        return self.cache_dir / f"{tool_key}.json"

    def read(self, tool_key: str) -> list[dict]:
        path = self._tool_path(tool_key)
        if not path.exists():
            return []
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def write(self, tool_key: str, releases: list[dict]) -> None:
        path = self._tool_path(tool_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(releases, f, indent=2)

    def merge(self, tool_key: str, new_releases: list[dict]) -> list[dict]:
        """Merge new releases into cache. Append-only: keeps old entries, adds new ones."""
        existing = self.read(tool_key)
        existing_versions = {r["version"] for r in existing}
        merged = list(existing)
        for release in new_releases:
            if release["version"] not in existing_versions:
                merged.append(release)
                existing_versions.add(release["version"])
        # Sort by date descending, then version
        merged.sort(key=lambda r: r.get("date", ""), reverse=True)
        self.write(tool_key, merged)
        return merged
