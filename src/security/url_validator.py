"""
URL Validator - проверка безопасности URL.

Предотвращает использование опасных схем URL:
- file:// - доступ к локальной файловой системе
- javascript: - выполнение произвольного JS
- data: - инъекция данных
- vbscript: - выполнение VBScript
"""

import logging
from urllib.parse import urlparse
from typing import Tuple

from ..constants import Security


logger = logging.getLogger(__name__)


class URLValidationError(Exception):
    """Ошибка валидации URL."""
    pass


class URLValidator:
    """
    Валидатор URL для безопасной навигации.
    
    Проверяет URL перед навигацией и блокирует
    потенциально опасные схемы.
    
    Example:
        ```python
        validator = URLValidator()
        
        # Безопасные URL
        validator.validate("https://google.com")  # OK
        validator.validate("http://localhost:3000")  # OK
        
        # Опасные URL - вызовут исключение
        validator.validate("file:///etc/passwd")  # URLValidationError
        validator.validate("javascript:alert(1)")  # URLValidationError
        ```
    """
    
    def __init__(
        self,
        allowed_schemes: set[str] | None = None,
        blocked_schemes: set[str] | None = None,
        allowed_special: set[str] | None = None
    ):
        """
        Инициализирует валидатор.
        
        Args:
            allowed_schemes: Разрешённые схемы (по умолчанию http, https)
            blocked_schemes: Явно запрещённые схемы
            allowed_special: Специальные разрешённые URL (например about:blank)
        """
        self.allowed_schemes = allowed_schemes or Security.ALLOWED_URL_SCHEMES
        self.blocked_schemes = blocked_schemes or Security.BLOCKED_URL_SCHEMES
        self.allowed_special = allowed_special or Security.ALLOWED_SPECIAL_URLS
    
    def validate(self, url: str) -> bool:
        """
        Проверяет URL на безопасность.
        
        Args:
            url: URL для проверки
            
        Returns:
            bool: True если URL безопасен
            
        Raises:
            URLValidationError: Если URL опасен или невалиден
        """
        if not url:
            raise URLValidationError("URL не может быть пустым")
        
        # Проверяем специальные разрешённые URL
        url_lower = url.lower().strip()
        if url_lower in self.allowed_special:
            logger.debug(f"URL разрешён как специальный: {url}")
            return True
        
        # Парсим URL
        try:
            parsed = urlparse(url)
        except Exception as e:
            raise URLValidationError(f"Невалидный URL: {url}. Ошибка: {e}")
        
        scheme = parsed.scheme.lower()
        
        # Проверяем на явно запрещённые схемы
        if scheme in self.blocked_schemes:
            logger.warning(f"Заблокирована опасная схема URL: {scheme}:// в {url}")
            raise URLValidationError(
                f"Схема URL '{scheme}' запрещена по соображениям безопасности. "
                f"Используйте http:// или https://"
            )
        
        # Проверяем, что схема в списке разрешённых
        if scheme and scheme not in self.allowed_schemes:
            logger.warning(f"Неразрешённая схема URL: {scheme}:// в {url}")
            raise URLValidationError(
                f"Схема URL '{scheme}' не разрешена. "
                f"Разрешённые схемы: {', '.join(self.allowed_schemes)}"
            )
        
        # Если схемы нет - добавляем https по умолчанию (не ошибка)
        if not scheme:
            logger.debug(f"URL без схемы, будет добавлен https://: {url}")
        
        logger.debug(f"URL прошёл валидацию: {url}")
        return True
    
    def is_safe(self, url: str) -> Tuple[bool, str]:
        """
        Проверяет URL и возвращает результат без исключения.
        
        Args:
            url: URL для проверки
            
        Returns:
            Tuple[bool, str]: (безопасен, сообщение об ошибке или пустая строка)
        """
        try:
            self.validate(url)
            return True, ""
        except URLValidationError as e:
            return False, str(e)
    
    def sanitize(self, url: str) -> str:
        """
        Санитизирует URL, добавляя схему если нужно.
        
        Args:
            url: URL для санитизации
            
        Returns:
            str: Санитизированный URL
            
        Raises:
            URLValidationError: Если URL опасен
        """
        # Сначала валидируем
        self.validate(url)
        
        # Добавляем схему если отсутствует
        url_stripped = url.strip()
        parsed = urlparse(url_stripped)
        
        if not parsed.scheme:
            return f"https://{url_stripped}"
        
        return url_stripped


# Глобальный экземпляр для удобства использования
_default_validator: URLValidator | None = None


def get_url_validator() -> URLValidator:
    """
    Возвращает глобальный экземпляр URLValidator.
    
    Returns:
        URLValidator: Глобальный валидатор
    """
    global _default_validator
    if _default_validator is None:
        _default_validator = URLValidator()
    return _default_validator


def validate_url(url: str) -> bool:
    """
    Удобная функция для валидации URL.
    
    Args:
        url: URL для проверки
        
    Returns:
        bool: True если URL безопасен
        
    Raises:
        URLValidationError: Если URL опасен
    """
    return get_url_validator().validate(url)


def is_url_safe(url: str) -> Tuple[bool, str]:
    """
    Удобная функция для проверки безопасности URL.
    
    Args:
        url: URL для проверки
        
    Returns:
        Tuple[bool, str]: (безопасен, сообщение)
    """
    return get_url_validator().is_safe(url)