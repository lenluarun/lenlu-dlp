@echo off
title LENLU DLP Startup Script

rem ============================================================
rem LENLU DLP - Retro Terminal Media Web GUI
rem Automatic requirement check and installation using Virtual Env
rem ============================================================

rem --- Check if virtual environment exists ---
if not exist ".venv\Scripts\activate.bat" (
    echo Virtual environment not found. Creating one...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to create virtual environment.
        echo Make sure Python is installed and in your PATH.
        pause
        exit /b 1
    )
)

rem --- Activate the virtual environment ---
echo Activating virtual environment...
call .venv\Scripts\activate.bat

rem --- Upgrade pip inside venv ---
echo Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 echo pip upgrade failed, continuing...

rem --- Install/upgrade Python requirements inside venv ---
echo Installing required Python packages...
python -m pip install --upgrade fastapi uvicorn yt-dlp
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed. Please check your internet connection.
    pause
    exit /b 1
)
echo Required packages installed/verified in .venv.

rem --- Check for ffmpeg (optional but recommended) ---
echo.
echo Checking for ffmpeg (recommended for media merging)...
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo ffmpeg not found - will be used if available, download optional.
    echo.
    echo ffmpeg is recommended for automatic audio/video format merging.
    echo You can download it from: https://ffmpeg.org
) else (
    echo ffmpeg found.
)

rem --- Start the local server ---
echo.
echo Starting LENLU DLP local server...
echo.
python run_gui.py
set EXIT_CODE=%errorlevel%

echo.
if %EXIT_CODE% neq 0 (
    echo [!] LENLU DLP exited with error code: %EXIT_CODE%
) else (
    echo [*] LENLU DLP server execution completed.
)
echo Press any key to close this terminal window...
pause >nul

rem Deactivate venv on exit
call deactivate

