"""
Browser Agent - AI-агент для автоматизации браузера.

Запуск:
    python main.py
    
Или через скрипты:
    Windows: run.bat
    Linux/Mac: ./run.sh

Требования:
    - Python 3.10+
    - Установленные зависимости: pip install -r requirements.txt
    - Playwright: playwright install chromium
    - API ключ Anthropic в .env файле
"""

import asyncio
import sys
import logging
from pathlib import Path

# Добавляем корневую директорию в путь
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from src.ui.cli import CLI


# Настройка логирования
def setup_logging(level: str = "INFO") -> None:
    """Настраивает логирование."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Уменьшаем шум от библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)


async def main() -> None:
    """Точка входа в приложение."""
    # Настраиваем логирование (можно изменить на DEBUG для отладки)
    setup_logging("WARNING")
    
    # Запускаем CLI
    cli = CLI()
    await cli.run()


def run() -> None:
    """Синхронная обёртка для запуска."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nВыход...")


if __name__ == "__main__":
    run()