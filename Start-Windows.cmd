@echo off
setlocal
cd /d "%~dp0"
python -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >nul 2>nul
if not errorlevel 1 (
    python run.py
    if errorlevel 1 pause
    exit /b
)
py -3 -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >nul 2>nul
if not errorlevel 1 (
    py -3 run.py
    if errorlevel 1 pause
    exit /b
)
echo Can cai Python 3.10 tro len, gom thanh phan Tcl/Tk.
echo Tai https://www.python.org/downloads/windows/
echo Sau khi cai dat, mo lai tep nay.
pause
