"""
Централизованные константы для browser-agent.

Все magic numbers и hardcoded values собраны здесь
для удобства настройки и поддержки.
"""

from typing import Set


class Timeouts:
    """Таймауты в миллисекундах."""
    
    # Навигация
    DEFAULT_PAGE = 30000  # Общий таймаут страницы
    NAVIGATION = 30000  # Ожидание навигации
    NETWORK_IDLE = 10000  # Ожидание network idle после навигации
    
    # Взаимодействие с элементами
    CLICK = 5000  # Ожидание элемента для клика
    ELEMENT_WAIT = 500  # Базовое ожидание элемента
    TYPE_TEXT = 5000  # Ожидание поля ввода
    
    # Скриншоты
    SCREENSHOT = 10000  # Таймаут для скриншота
    SCREENSHOT_FALLBACK = 5000  # Fallback для viewport-only скриншота
    
    # Ожидание в агенте
    WAIT_DEFAULT = 500  # Дефолтный wait между действиями
    WAIT_MAX = 500  # Максимальный wait (для агрессивной оптимизации)


class Retries:
    """Настройки повторных попыток."""
    
    MAX_RETRIES = 3  # Максимум попыток
    BASE_DELAY = 0.5  # Базовая задержка в секундах (exponential backoff)
    
    # Множители для exponential backoff
    # Попытка 1: 0.5s, Попытка 2: 1.0s, Попытка 3: 2.0s
    MULTIPLIER = 2


class Limits:
    """Лимиты для предотвращения переполнения."""
    
    # DOM и элементы - ОПТИМИЗИРОВАНО для экономии токенов
    MAX_DOM_SIZE = 4000  # Уменьшено с 6000 - экономия ~30% токенов
    MAX_ELEMENTS = 30  # Уменьшено с 40 - экономия ~25% токенов
    MAX_TEXT_LENGTH = 100  # Уменьшено с 200 - экономия ~50% на текстах
    MAX_SELECTOR_LENGTH = 60  # Уменьшено с 80
    MAX_CLASS_LENGTH = 40  # Уменьшено с 60
    
    # История и сообщения - КРИТИЧЕСКАЯ оптимизация
    MAX_MESSAGE_HISTORY = 4  # Уменьшено с 6 - экономия ~33% на истории
    MAX_HISTORY = 15  # Уменьшено с 20
    
    # Итерации и время
    MAX_ITERATIONS = 30  # Уменьшено с 50 - предотвращает runaway costs
    TASK_TIMEOUT_SECONDS = 300  # Уменьшено с 600 (5 минут вместо 10)


class LoopDetection:
    """Настройки детекции зацикливания."""
    
    MAX_REPEATED_ACTIONS = 3  # Порог повторения одного действия
    PATTERN_LENGTH = 6  # Длина паттерна для анализа
    ALTERNATION_CHECK = 4  # Количество действий для проверки A-B-A-B


class Security:
    """Настройки безопасности."""
    
    # Разрешённые схемы URL
    ALLOWED_URL_SCHEMES: Set[str] = {"http", "https"}
    
    # Запрещённые схемы (явный blacklist)
    BLOCKED_URL_SCHEMES: Set[str] = {
        "file",
        "javascript",
        "data",
        "vbscript",
        "about",  # кроме about:blank
    }
    
    # Разрешённые исключения
    ALLOWED_SPECIAL_URLS: Set[str] = {"about:blank"}


class PageAnalysis:
    """Настройки анализа страниц."""
    
    # Глубина DOM
    MAX_DEPTH = 6
    MAX_CHILDREN = 20
    
    # Текстовый контент
    MAX_TEXT_CONTENT_LENGTH = 2000
    
    # Viewport fallback
    DEFAULT_VIEWPORT_WIDTH = 1280
    DEFAULT_VIEWPORT_HEIGHT = 800


class TokenOptimization:
    """Настройки оптимизации токенов."""
    
    # Compact prompts
    USE_COMPACT_PROMPTS = True
    
    # Размеры контента - ОПТИМИЗИРОВАНО
    DOM_SIZE_COMPACT = 3000  # Уменьшено с 6000 - экономия 50%
    ELEMENTS_COUNT_COMPACT = 25  # Уменьшено с 40 - экономия ~40%
    TEXT_CONTENT_COMPACT = 1500  # Уменьшено с 2500 - экономия 40%
    
    # Cost control - NEW
    MAX_COST_PER_TASK_USD = 0.50  # Максимальная стоимость одной задачи
    WARN_COST_THRESHOLD_USD = 0.25  # Порог предупреждения о стоимости


class HumanLikeDelays:
    """
    Human-like delay ranges to avoid bot detection.
    
    All values are in milliseconds (ms).
    Convert to seconds when using: delay_ms / 1000
    """
    
    # Click action delays (ms)
    CLICK_MIN = 300
    CLICK_MAX = 800
    
    # Typing delays per character (ms)
    TYPE_MIN = 50
    TYPE_MAX = 150
    
    # Navigation post-load delay (ms)
    NAVIGATE_MIN = 500
    NAVIGATE_MAX = 1500
    
    # Scroll action delays (ms)
    SCROLL_MIN = 200
    SCROLL_MAX = 600
    
    # Mouse movement micro-delays (ms)
    MOUSE_STEP_MIN = 10
    MOUSE_STEP_MAX = 30
    MOUSE_STEPS_MIN = 5
    MOUSE_STEPS_MAX = 15