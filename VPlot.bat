@echo off
cd /d "%~dp0"
pythonw -m vplot 2>nul || python -m vplot
