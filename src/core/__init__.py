"""
Core модуль Browser Agent.

Содержит основные компоненты агента:
- BrowserAgent: Главный класс агента
- TaskManager: Управление задачами
- ContextManager: Управление контекстом и историей
- SecurityLayer: Слой безопасности (импортируется из security модуля)
"""

from .agent import BrowserAgent
from .task_manager import TaskManager, TaskStatus
from .context_manager import ContextManager
from ..security.security_layer import SecurityLayer

__all__ = [
    "BrowserAgent",
    "TaskManager",
    "TaskStatus",
    "ContextManager",
    "SecurityLayer",
]