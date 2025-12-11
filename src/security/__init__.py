"""
Security модуль Browser Agent.

Содержит SecurityLayer для проверки опасных действий
и запроса подтверждения пользователя.
"""

from .security_layer import SecurityLayer

__all__ = [
    "SecurityLayer",
]