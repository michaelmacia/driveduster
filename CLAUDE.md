# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

DriveDuster is a Windows desktop GUI app that scans and visualizes directory sizes to help users free up disk space. It is a single-file Python app (`driveduster.py`) using only stdlib (tkinter), so no pip installs are needed at runtime.

## Running and building

```bash
# Run directly (requires Python 3.11+)
python driveduster.py

# Build standalone Windows executable (dev only)
build.bat
# Output: dist/DriveDuster.exe
```

`requirements.txt` lists only `pyinstaller` (build-time only). The app itself has zero third-party dependencies.

## Architecture

Everything lives in `driveduster.py`:

- **`get_dir_size(path)`** — recursive size calculation; swallows `PermissionError`/`OSError` silently.
- **`scan_children(path)`** — scans immediate subdirectories of a path using a 16-worker `ThreadPoolExecutor`, returns results sorted largest-first.
- **`DriveDusterApp`** — single class containing the full UI and scan logic.

## Tree / lazy-loading model

The `ttk.Treeview` is hierarchical. Every inserted directory node gets a sentinel placeholder child (`_DUMMY` prefix iid) so the expand arrow appears. When the user expands a node (`<<TreeviewOpen>>`):

1. `_on_expand()` detects the placeholder child and starts a background thread.
2. `_expand_worker()` calls `scan_children()` for that node's path.
3. `_on_expand_done()` (main thread via `root.after`) removes the placeholder and inserts real children, each with their own placeholder.

Root-level scans use a `_root_gen` integer counter. When a new root scan starts the counter increments; stale workers compare their captured `gen` against `self._root_gen` and discard results if they don't match. Node-expansion scans are tracked in `self._expanding: set[str]` to prevent double-scanning.

## Key behaviours

- `% of parent` column shows size relative to the sibling group total at each level.
- Color tags (`huge`/`large`/`medium`/`small`) are applied per-row based on GB thresholds (10 / 1 / 0.1 GB).
- Right-clicking a row opens a context menu; clicking the placeholder row is ignored.
