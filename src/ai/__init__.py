"""
AI модуль для Browser Agent.

Содержит компоненты для взаимодействия с LLM (Claude API):
- LLMClient: Клиент для отправки сообщений и обработки tool calls
- BROWSER_TOOLS: Определения инструментов для function calling
- Промпты: Системные промпты для агента
"""

from .llm_client import LLMClient
from .tools import BROWSER_TOOLS, get_tool_by_name
from .prompts import SYSTEM_PROMPT, build_task_prompt

__all__ = [
    "LLMClient",
    "BROWSER_TOOLS",
    "get_tool_by_name",
    "SYSTEM_PROMPT",
    "build_task_prompt",
]