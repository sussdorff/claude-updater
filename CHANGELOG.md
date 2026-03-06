# Changelog

All notable changes to claude-updater will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Documentation

- Update changelog

### Fixed

- Enable self-update via uv tool upgrade
- Invalidate version cache after update and fix stale self-version detection

## [2026.03.5] - 2026-03-03

### Added

- Add remote version checking and updating via SSH
- Add post-update hooks and refactor remote helpers

### Documentation

- Update changelog

### Bd

- Backup 2026-03-02 15:21
- Backup 2026-03-03 03:43
- Backup 2026-03-03 04:23

## [2026.03.4] - 2026-03-02

### Added

- Remove unused AI summary feature

### Documentation

- Update changelog for v2026.03.1-3 releases
- Update changelog

### Bd

- Backup 2026-03-02 14:52

## [2026.03.3] - 2026-03-02

### Fixed

- Normalize CalVer leading zeros in self-check adapter

## [2026.03.2] - 2026-03-02

### Added

- Add self-check adapter for claude-updater

## [2026.03.1] - 2026-03-02

### Added

- Improve dolt release notes extraction, remove beads CLI adapter

### Bd

- Backup 2026-03-02 09:16

## [2026.03.0] - 2026-03-02

### Added

- Add release-notes subcommand with date filtering and cache

### Documentation

- Update changelog
- Update changelog for release-notes feature

### Maintenance

- Add beads prime directive and agents instructions

### Bd

- Backup 2026-03-02 08:34
- Backup 2026-03-02 08:54

## [0.3.1] - 2026-03-02

### Added

- Initial implementation of claude-updater
- Show release notes during check and update

### Fixed

- Accurate version detection and PyPI publishing setup
- Move pytest to dependency-groups for uv compatibility
- Stamp version in __init__.py during release

