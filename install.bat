@echo off
chcp 65001 >nul 2>&1
echo ======================================
echo        VPlot Installer  v1.0.0
echo ======================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: python not found. Please install Python 3.9+.
    pause
    exit /b 1
)

python -c "import tkinter" 2>nul
if errorlevel 1 (
    echo ERROR: tkinter not available. Reinstall Python with "tcl/tk" option checked.
    pause
    exit /b 1
)

echo [+] Installing VPlot ...
pip install "%~dp0"
if errorlevel 1 (
    echo.
    echo Install failed. Try:  pip install --user "%~dp0"
    pause
    exit /b 1
)

echo.
echo ======================================
echo   Install complete!
echo   Launch with:  vp
echo   Or:           python -m vplot
echo ======================================
pause
