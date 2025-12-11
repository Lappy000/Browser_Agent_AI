"""
Конфигурация приложения.

Модуль содержит настройки для браузерной автоматизации и AI,
загружаемые из переменных окружения.
"""

import os
from pathlib import Path
from typing import Literal, Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()


@dataclass
class VisionConfig:
    """Конфигурация режима Vision (скриншоты для LLM)."""
    
    # Включить режим vision (отправка скриншотов в LLM)
    # ВНИМАНИЕ: Vision значительно увеличивает стоимость (в 5-10 раз)
    enabled: bool = True
    
    # Частота захвата скриншотов:
    # "always" - каждую итерацию (ДОРОГО! ~$0.01-0.02 за скриншот)
    # "on_navigation" - только после навигации (РЕКОМЕНДУЕТСЯ - экономия 70-80%)
    # "on_error" - только при ошибках (максимальная экономия)
    frequency: Literal["always", "on_navigation", "on_error"] = "on_navigation"
    
    # Захватывать всю страницу (не только viewport)
    full_page: bool = False
    
    # Максимальная ширина скриншота (для экономии токенов)
    # Уменьшение размера существенно снижает стоимость vision tokens
    max_width: int = 1024  # Уменьшено с 1280
    
    # Максимальная высота скриншота
    max_height: int = 768  # Уменьшено с 800
    
    # Качество JPEG сжатия (0-100, только если use_jpeg=True)
    jpeg_quality: int = 70
    
    # Использовать JPEG вместо PNG (меньше токенов, но потеря качества)
    use_jpeg: bool = True


@dataclass
class BrowserConfig:
    """Конфигурация браузера."""
    
    # Тип браузера: chromium, firefox или webkit
    browser_type: Literal["chromium", "firefox", "webkit"] = "chromium"
    
    # Запускать браузер в headless режиме (без UI)
    headless: bool = False
    
    # Директория для хранения данных пользователя (cookies, localStorage)
    user_data_dir: Path = field(default_factory=lambda: Path("./user_data"))
    
    # Размер viewport
    viewport_width: int = 1280
    viewport_height: int = 800
    
    # Задержка между действиями в мс (для визуальной отладки) - минимизирована для скорости
    slow_mo: int = 10  # Reduced from 50 (80% faster)
    
    # Таймаут по умолчанию для ожидания элементов (мс) - агрессивно оптимизировано для скорости
    default_timeout: int = 3000  # Reduced from 10000 (70% faster)
    
    # Таймаут навигации (мс) - оптимизирован для быстрой загрузки
    navigation_timeout: int = 5000  # Reduced from 60000 (83% faster)


@dataclass
class Config:
    """Основная конфигурация приложения."""
    
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    
    # Уровень логирования
    log_level: str = "INFO"
    
    # Максимальный размер упрощённого DOM (символов) - увеличено для сложных страниц
    max_dom_size: int = 15000
    
    # Security Layer настройки
    security_enabled: bool = True
    
    # AI API настройки
    # Provider: "anthropic", "openrouter", or "custom"
    ai_provider: str = "anthropic"
    
    # Anthropic API настройки
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    
    # OpenRouter API настройки
    openrouter_api_key: Optional[str] = None
    openrouter_model: str = "anthropic/claude-sonnet-4.5"
    
    # Custom endpoint настройки
    custom_api_base_url: str = ""
    custom_api_key: Optional[str] = None
    llm_model: str = "claude-sonnet-4-latest"
    
    # Настройки агента - увеличено для сложных задач
    max_iterations: int = 40  # Увеличено для сложных задач
    task_timeout: int = 600  # 10 минут для сложных задач
    
    # Show LLM thinking/reasoning in console
    show_thinking: bool = True
    
    # Log display mode: "compact" or "verbose"
    # compact - simple action display (● Клик на элемент #15)
    # verbose - full tool details (Using tool: click_element {...})
    log_mode: str = "compact"
    
    @classmethod
    def from_env(cls) -> "Config":
        """
        Создаёт конфигурацию из переменных окружения.
        
        Returns:
            Config: Объект конфигурации с настройками из .env
        """
        browser_config = BrowserConfig(
            browser_type=os.getenv("BROWSER_TYPE", "chromium"),
            headless=os.getenv("HEADLESS", "false").lower() == "true",
            user_data_dir=Path(os.getenv("USER_DATA_DIR", "./user_data")),
            viewport_width=int(os.getenv("VIEWPORT_WIDTH", "1280")),
            viewport_height=int(os.getenv("VIEWPORT_HEIGHT", "800")),
            slow_mo=int(os.getenv("SLOW_MO", "10")),
            default_timeout=int(os.getenv("DEFAULT_TIMEOUT", "3000")),
            navigation_timeout=int(os.getenv("NAVIGATION_TIMEOUT", "5000")),
        )
        
        # Vision config for screenshot-based AI mode
        # DEFAULT: on_navigation для экономии токенов
        vision_frequency = os.getenv("VISION_FREQUENCY", "on_navigation")
        if vision_frequency not in ("always", "on_navigation", "on_error"):
            vision_frequency = "on_navigation"
        
        vision_config = VisionConfig(
            enabled=os.getenv("VISION_ENABLED", "true").lower() == "true",
            frequency=vision_frequency,
            full_page=os.getenv("VISION_FULL_PAGE", "false").lower() == "true",
            max_width=int(os.getenv("VISION_MAX_WIDTH", "1024")),
            max_height=int(os.getenv("VISION_MAX_HEIGHT", "768")),
            jpeg_quality=int(os.getenv("VISION_JPEG_QUALITY", "70")),
            use_jpeg=os.getenv("VISION_USE_JPEG", "true").lower() == "true",
        )
        
        return cls(
            browser=browser_config,
            vision=vision_config,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            max_dom_size=int(os.getenv("MAX_DOM_SIZE", "10000")),
            security_enabled=os.getenv("SECURITY_ENABLED", "true").lower() == "true",
            ai_provider=os.getenv("AI_PROVIDER", "anthropic"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
            openrouter_model=os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5"),
            custom_api_base_url=os.getenv("CUSTOM_API_BASE_URL", ""),
            custom_api_key=os.getenv("CUSTOM_API_KEY"),
            llm_model=os.getenv("LLM_MODEL", "claude-sonnet-4-latest"),
            max_iterations=int(os.getenv("MAX_ITERATIONS", "40")),
            task_timeout=int(os.getenv("TASK_TIMEOUT", "600")),
            show_thinking=os.getenv("SHOW_THINKING", "true").lower() == "true",
            log_mode=os.getenv("LOG_MODE", "compact"),
        )


# Глобальный экземпляр конфигурации
_config: Config | None = None


def get_config() -> Config:
    """
    Получает глобальный экземпляр конфигурации.
    
    Returns:
        Config: Объект конфигурации
    """
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reset_config() -> None:
    """Сбрасывает глобальную конфигурацию (для тестов)."""
    global _config
    _config = None