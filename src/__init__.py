"""
Browser Agent - AI-powered browser automation module.

Этот модуль предоставляет компоненты для автоматизации браузера
с использованием Playwright и AI для принятия решений.
"""

from .config import Config

# Browser module
from .browser import BrowserController, PageAnalyzer, SessionManager

# AI module
from .ai import LLMClient, BROWSER_TOOLS, SYSTEM_PROMPT

# Core module
from .core import BrowserAgent, TaskManager, ContextManager

# Security module
from .security import SecurityLayer

# UI module
from .ui import CLI

__version__ = "1.0.0"
__all__ = [
    # Config
    "Config",
    # Browser
    "BrowserController",
    "PageAnalyzer",
    "SessionManager",
    # AI
    "LLMClient",
    "BROWSER_TOOLS",
    "SYSTEM_PROMPT",
    # Core
    "BrowserAgent",
    "TaskManager",
    "ContextManager",
    # Security
    "SecurityLayer",
    # UI
    "CLI",
]