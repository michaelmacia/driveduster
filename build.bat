@echo off
pip install pyinstaller >nul 2>&1
pyinstaller --onefile --windowed --name DriveDuster driveduster.py
echo.
echo Done. Executable: dist\DriveDuster.exe
