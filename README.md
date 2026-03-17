# DriveDuster

Windows desktop app for visualizing directory sizes and finding what's eating your disk space.

![screenshot placeholder](docs/screenshot.png)

## Download

Grab the latest `DriveDuster.exe` from [Releases](../../releases/latest) — no installation required, just run it.

## Usage

- **Double-click** a directory to drill into it
- **◀ Back / ▲ Up** to navigate back up the tree
- **Drive dropdown** to switch drives
- **Click column headers** to sort
- **Right-click** a row to open in Explorer or copy the path

## Build from source

Requires Python 3.11+.

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name DriveDuster driveduster.py
# Output: dist/DriveDuster.exe
```

Or just run `build.bat`.
