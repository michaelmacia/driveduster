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

- **`get_dir_size(path)`** — recursive size calculation; swallows `PermissionError`/`OSError` silently so restricted folders don't break the scan.
- **`DriveDusterApp`** — single class containing the full UI and scan logic.
  - `navigate_to()` is the central navigation method; all drive/path/back/up/double-click actions funnel through it.
  - `_start_scan()` → `_scan_worker()` (background thread, 16-worker `ThreadPoolExecutor`) → `_on_scan_done()` (back on main thread via `root.after`). The `_cancel` flag aborts in-flight scans when a new navigation happens.
  - `_populate_tree()` renders results into the `ttk.Treeview`; call it again after sorting to re-render.

## Key behaviours

- Scanning runs on a daemon thread; UI stays responsive. Results are posted back with `root.after(0, ...)`.
- A new navigation while a scan is in progress sets `self._cancel = True`; the worker checks this flag between futures and exits early.
- Column header clicks toggle sort direction; sort state is stored in `_sort_col` / `_sort_desc`.
- Color tags (`huge`/`large`/`medium`/`small`) are applied per-row based on GB thresholds (10 / 1 / 0.1 GB).
