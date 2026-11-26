# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-26

First public release, branded **PinDesk**.

### Added

- Create tab with folder/file browsing, auto-detection, live preview and **Add launcher**.
- Manage tab with icons, edit, remove, open-folder and **Fix moved app folders…**.
- Local-only icon discovery: app folders, launch-script references, installed icon themes and generated initials SVG.
- Native file dialogs via `kdialog`, `zenity` or `yad`, with a Tk fallback.
- Optional menu entry installer and uninstaller (`install.sh`, `uninstall.sh`).
- Single fixed dark theme with plain rectangular widgets.
- 19 offline tests and GitHub Actions test workflow.
- Full documentation: usage, FAQ, troubleshooting, internals, contributing and security policy.

### Changed

- Renamed from "Portable Launcher Maker" to PinDesk.
- Configuration moved from `~/.config/portable-launcher/` to `~/.config/pindesk/`
  with automatic migration of existing settings and launcher registry.

[1.0.0]: https://github.com/F1tixx/PinDesk/releases/tag/v1.0.0
