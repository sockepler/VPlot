@echo off
cd /d "%~dp0"
set PYTHONPATH=%~dp0;%PYTHONPATH%
pythonw -m vplot 2>nul || python -m vplot
