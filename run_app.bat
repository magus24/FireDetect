@echo off
title FireDtect Mission Control Launcher
cd /d "%~dp0"

echo =======================================================
echo      FireDtect Autonomous Drone Mission Control
echo   RTX 3070 Ti Laptop GPU + Edge Vision Subsystem
echo =======================================================
echo.

:: Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment 'venv' not found.
    echo [SETUP] Creating isolated environment and installing dependencies...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Python not found or failed to create venv! Please install Python 3.10 or 3.11.
        pause
        exit /b 1
    )
    call venv\Scripts\activate.bat
    echo [SETUP] Installing PyTorch with CUDA 12.1 for RTX 3070 Ti...
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    echo [SETUP] Installing remaining dependencies...
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo.
echo [LAUNCH] Starting FireDtect Edge AI Application...
echo.
python src/main.py %*

if errorlevel 1 (
    echo.
    echo [ERROR] Application exited with an error.
    pause
)
