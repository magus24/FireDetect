@echo off
title FireDetect - Mission Control Launcher
cd /d "%~dp0"

echo =================================================================
echo       FireDetect: Autonomous Firefighting Drone (Edge AI MVP)
echo =================================================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [SETUP] Virtual environment 'venv' not found.
    echo         Run install_dependencies.bat first to set it up.
    echo.
    pause
    exit /b 1
)

echo [1/2] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Could not activate venv.
    pause
    exit /b 1
)

echo [2/2] Launching Mission Control (src/main.py)...
echo.
echo -----------------------------------------------------------------
echo Controls:
echo   [SPACE]  - Manual drop test (servo 0 -^> 90 -^> 0)
echo   [C]      - Switch camera index
echo   [M]      - Toggle demo / desk test mode
echo   [S]      - Toggle sound
echo   [Q]      - Quit
echo -----------------------------------------------------------------
echo.

if "%~1"=="" (
    python src/main.py --demo
) else (
    python src/main.py %*
)

if errorlevel 1 (
    echo.
    echo [ERROR] The application exited with an error.
    pause
)
