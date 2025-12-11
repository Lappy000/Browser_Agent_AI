#!/bin/bash
# Browser Agent - Скрипт запуска для Linux/Mac
# Запускает AI-агента для автоматизации браузера

# Переходим в директорию скрипта
cd "$(dirname "$0")"

echo ""
echo "========================================"
echo "  Browser Agent - Запуск"
echo "========================================"
echo ""

# Проверяем наличие Python
if ! command -v python3 &> /dev/null; then
    echo "[ОШИБКА] Python3 не найден!"
    echo "Установите Python 3.10+ для вашей системы."
    exit 1
fi

# Проверяем наличие .env файла
if [ ! -f ".env" ]; then
    echo "[ПРЕДУПРЕЖДЕНИЕ] Файл .env не найден!"
    echo "Создайте .env файл на основе .env.example"
    echo "и добавьте ваш ANTHROPIC_API_KEY."
    echo ""
fi

# Запускаем агента
python3 main.py