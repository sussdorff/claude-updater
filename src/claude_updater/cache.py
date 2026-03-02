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
