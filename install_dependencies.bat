@echo off
chcp 65001 > nul
title FireDtect - Установка зависимостей
cd /d "%~dp0"

echo =================================================================
echo        FireDtect: Первоначальная установка и настройка
echo =================================================================
echo.

:: 1. Проверка наличия Python в системе
python --version > nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не обнаружен в системе!
    echo Установите Python 3.10, 3.11 или 3.12 с официального сайта python.org
    echo ОБЯЗАТЕЛЬНО поставьте галочку "Add Python to PATH" при установке.
    echo.
    pause
    exit /b 1
)

echo [1/4] Проверка Python: УСПЕШНО.
python --version

:: 2. Создание виртуального окружения venv, если его нет
if not exist "venv\Scripts\activate.bat" (
    echo.
    echo [2/4] Создание чистого виртуального окружения (venv)...
    python -m venv venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать виртуальное окружение.
        pause
        exit /b 1
    )
    echo Виртуальное окружение venv успешно создано.
) else (
    echo.
    echo [2/4] Виртуальное окружение venv уже существует.
)

:: 3. Активация виртуального окружения
echo.
echo [3/4] Активация виртуального окружения...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ОШИБКА] Не удалось активировать виртуальное окружение!
    pause
    exit /b 1
)
echo Окружение активно: %VIRTUAL_ENV%

:: Обновление pip
echo.
echo Обновление менеджера пакетов pip...
python -m pip install --upgrade pip

:: 4. Установка PyTorch с поддержкой CUDA для GPU (RTX 3070 Ti)
echo.
echo [4/4] Установка PyTorch с поддержкой CUDA 12.1 для видеокарты...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
if errorlevel 1 (
    echo [ВНИМАНИЕ] Ошибка установки CUDA PyTorch. Пробуем установить базовый CPU PyTorch...
    pip install torch torchvision torchaudio
)

:: Установка остальных зависимостей
echo.
echo Установка остальных зависимостей из requirements.txt...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить некоторые библиотеки из requirements.txt!
    pause
    exit /b 1
)

echo.
echo =================================================================
echo   [УСПЕХ] Все зависимости успешно установлены!
echo   Теперь вы можете запускать проект через файл: start_app.bat
echo =================================================================
echo.
pause
