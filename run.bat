@echo off
REM Browser Agent - Скрипт запуска для Windows
REM Запускает AI-агента для автоматизации браузера

cd /d "%~dp0"

echo.
echo ========================================
echo   Browser Agent - Запуск
echo ========================================
echo.

REM Проверяем наличие Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден!
    echo Установите Python 3.10+ и добавьте в PATH.
    pause
    exit /b 1
)

REM Проверяем наличие .env файла
if not exist ".env" (
    echo [ПРЕДУПРЕЖДЕНИЕ] Файл .env не найден!
    echo Создайте .env файл на основе .env.example
    echo и добавьте ваш ANTHROPIC_API_KEY.
    echo.
)

REM Запускаем агента
python main.py

pause