"""Multi-tool update checker for the Claude Code ecosystem."""

try:
    from importlib.metadata import version as _get_version
    __version__ = _get_version("claude-updater")
except Exception:
    __version__ = "0.0.0.dev0"
