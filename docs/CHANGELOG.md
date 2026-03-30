# Changelog

This file tracks user-facing product changes by release.

## 0.2.2

Based on commit: `3c36204` (`[feat] Grant Claude Code write access to the system`)

### Highlights

- Claude Code can now run with system write access when configured to do so.
- Added an in-card **Stop** control for live AI replies in Feishu.

### Details

- Added Claude-side permission handling for write-capable runs.
- Wired the new Claude permission settings through runtime config and TUI.
- Added a Stop button to streaming answer cards so users can interrupt a running reply without using text commands.


## 0.2.0

Based on commit: `0f48a50` (`[refactor] streamline relay and bootstrap flows`)

### Highlights

- Added **Claude Code** as a first-class agent alongside Codex.
- Added **Feishu interactive cards** as a core part of the product flow.

### Details

- Introduced a modular relay architecture to replace the old monolithic bridge implementation.
- Added provider abstraction for both Codex and Claude Code.
- Added Feishu bootstrap automation.
- Reworked the TUI into a structured menu-driven configuration flow.
- Added relay support modules for cards, messaging, runtime, stores, and utilities.


## 0.1.0

Based on commit: `70e46d4` (`[init] bootstrap poco project`)

### Highlights

- First public bootstrap of PoCo with **Codex** support.

### Details

- Added the initial PoCo project structure.
- Added the initial Feishu relay runtime.
- Added the initial config store and runtime service layer.
- Added the first Textual TUI.
- Added English and Chinese README files.
- Added packaging metadata and the dependency lockfile.
