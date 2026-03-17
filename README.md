# DriveDuster

Windows desktop app for visualizing directory sizes and finding what's eating your disk space.

<img width="1002" height="672" alt="image" src="https://github.com/user-attachments/assets/22cc0382-be4d-4cdb-88c2-945f6a032fe4" />


## Download

Grab the latest `DriveDuster.exe` from [Releases](../../releases/latest) — no installation required, just run it.

## Usage

- **Double-click** a directory to drill into it
- **◀ Back / ▲ Up** to navigate back up the tree
- **Drive dropdown** to switch drives
- **Click column headers** to sort
- **Right-click** a row to open in Explorer, copy the path, delete the folder, or uninstall the application
- **Drag column borders** to resize columns

## Build from source

Requires Python 3.11+.

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name DriveDuster driveduster.py
# Output: dist/DriveDuster.exe
```

Or just run `build.bat`.
