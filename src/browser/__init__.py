"""
Browser automation module.

Модуль браузерной автоматизации с использованием Playwright.
Включает контроллер браузера, анализатор страниц и менеджер сессий.
"""

from .controller import BrowserController
from .page_analyzer import PageAnalyzer
from .session_manager import SessionManager

__all__ = [
    "BrowserController",
    "PageAnalyzer", 
    "SessionManager"
]