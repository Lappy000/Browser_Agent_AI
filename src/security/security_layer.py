"""
SecurityLayer - слой безопасности для Browser Agent.

Проверяет действия перед выполнением и запрашивает
подтверждение для опасных операций.
"""

import re
import logging
from typing import Optional, Dict, Any, Callable, Awaitable, Tuple

logger = logging.getLogger(__name__)


class SecurityLayer:
    """
    Слой безопасности - проверяет действия перед выполнением
    и запрашивает подтверждение для опасных операций.
    
    Attributes:
        confirmation_callback: Async функция для запроса подтверждения
        
    Example:
        ```python
        security = SecurityLayer(
            confirmation_callback=cli.confirm_action
        )
        
        allowed, reason = await security.check_action(
            action="Клик по кнопке 'Оплатить'",
            tool_name="click",
            tool_input={"selector": "#pay-button"},
            page_context={"url": "https://shop.com/checkout"}
        )
        
        if allowed:
            await browser.click("#pay-button")
        else:
            print(f"Действие заблокировано: {reason}")
        ```
    """
    
    # Паттерны опасных действий
    DANGEROUS_PATTERNS = {
        "payment": [
            "оплат", "pay", "checkout", "купить", "buy", "заказ", "order",
            "payment", "purchase", "плат", "покупк"
        ],
        "delete": [
            "удал", "delete", "remove", "trash", "корзин", "erase", "уничтож",
            "очистить", "clear all", "remove all"
        ],
        "send": [
            "отправ", "send", "submit", "publish", "опубликов", "post",
            "отослать", "послать"
        ],
        "personal_data": [
            "пароль", "password", "card", "карт", "cvv", "cvc", "pin",
            "секрет", "secret", "token", "ключ", "key", "credentials"
        ],
        "account": [
            "выход", "logout", "sign out", "выйти", "аккаунт удал",
            "delete account", "закрыть аккаунт", "close account"
        ]
    }
    
    # URL паттерны высокого риска
    DANGEROUS_URL_PATTERNS = [
        r"checkout", r"payment", r"pay\.", r"order", r"cart",
        r"billing", r"subscribe", r"premium"
    ]
    
    # Инструменты и их базовый риск
    TOOL_BASE_RISK = {
        "navigate": "safe",
        "click": "low",  # Зависит от контекста
        "type_text": "low",  # Зависит от контекста
        "select_option": "low",
        "scroll": "safe",
        "wait": "safe",
        "extract_data": "safe",
        "go_back": "safe",
        "refresh": "safe",
        "take_screenshot": "safe",
        "complete_task": "safe",
        "ask_user": "safe"
    }
    
    def __init__(
        self,
        confirmation_callback: Optional[Callable[[str, str], Awaitable[bool]]] = None
    ):
        """
        Инициализирует SecurityLayer.
        
        Args:
            confirmation_callback: Async функция для запроса подтверждения.
                Принимает (action_description, risk_reason) и возвращает bool.
                Если None - используется input() в консоли.
        """
        self._confirmation_callback = confirmation_callback
        self._skip_confirmations = False
        
        logger.info("SecurityLayer инициализирован")
    
    def set_confirmation_callback(
        self,
        callback: Callable[[str, str], Awaitable[bool]]
    ) -> None:
        """Устанавливает callback для подтверждений."""
        self._confirmation_callback = callback
    
    def set_skip_confirmations(self, skip: bool) -> None:
        """
        Устанавливает режим пропуска подтверждений.
        
        ВНИМАНИЕ: Используйте только для тестирования!
        """
        self._skip_confirmations = skip
        if skip:
            logger.warning("⚠️ Подтверждения отключены! Только для тестирования.")
    
    async def check_action(
        self,
        action: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        page_context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Проверяет действие на опасность.
        
        Args:
            action: Описание действия
            tool_name: Имя инструмента
            tool_input: Параметры инструмента
            page_context: Контекст страницы (url, title, elements и т.д.)
            
        Returns:
            Tuple[bool, str]: (разрешено, причина)
            
        Example:
            ```python
            allowed, reason = await security.check_action(
                action="Клик по кнопке 'Удалить'",
                tool_name="click",
                tool_input={"selector": ".delete-btn"},
                page_context={"url": "https://example.com"}
            )
            ```
        """
        # Определяем уровень риска
        risk_level, risk_reason = self.assess_risk(tool_name, tool_input, page_context)
        
        logger.debug(
            f"Проверка действия: {action}, "
            f"tool={tool_name}, risk={risk_level}, reason={risk_reason}"
        )
        
        # Safe действия проходят без вопросов
        if risk_level == "safe":
            return True, "Действие безопасно"
        
        # Medium и High требуют подтверждения
        if risk_level in ("medium", "high"):
            # Формируем описание для пользователя
            action_desc = self._format_action_description(
                action, tool_name, tool_input, page_context
            )
            
            # Запрашиваем подтверждение
            confirmed = await self.request_confirmation(action_desc, risk_reason)
            
            if confirmed:
                logger.info(f"✓ Действие подтверждено пользователем: {action}")
                return True, "Подтверждено пользователем"
            else:
                logger.warning(f"✗ Действие отклонено пользователем: {action}")
                return False, "Отклонено пользователем"
        
        # Low risk - разрешаем
        return True, "Низкий риск, подтверждение не требуется"
    
    def assess_risk(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        page_context: Dict[str, Any]
    ) -> Tuple[str, str]:
        """
        Оценивает уровень риска действия.
        
        Args:
            tool_name: Имя инструмента
            tool_input: Параметры инструмента
            page_context: Контекст страницы
            
        Returns:
            Tuple[str, str]: (risk_level, reason)
            risk_level: "safe", "low", "medium", "high"
        """
        url = page_context.get("url", "")
        
        # 1. Проверяем navigate на опасные URL
        if tool_name == "navigate":
            target_url = tool_input.get("url", "")
            if self._is_dangerous_url(target_url):
                return "medium", f"Переход на страницу оплаты/заказа: {target_url}"
            return "safe", ""
        
        # 2. Проверяем click
        if tool_name == "click":
            # Проверяем текст элемента, если доступен
            element_text = self._get_element_text(tool_input, page_context)
            
            # Проверяем на опасные паттерны
            for category, patterns in self.DANGEROUS_PATTERNS.items():
                if self._matches_patterns(element_text, patterns):
                    return "high", f"Клик на элемент с опасным действием ({category}): '{element_text}'"
            
            # Проверяем контекст URL
            if self._is_dangerous_url(url):
                return "medium", f"Клик на странице оплаты/заказа"
            
            return "low", ""
        
        # 3. Проверяем type_text
        if tool_name == "type_text":
            text = tool_input.get("text", "")
            selector = tool_input.get("selector", "")
            
            # Проверяем, не вводим ли опасные данные
            if self._is_sensitive_field(selector, page_context):
                return "medium", f"Ввод данных в чувствительное поле"
            
            # Проверяем содержимое текста
            for category, patterns in self.DANGEROUS_PATTERNS.items():
                if category == "personal_data" and self._matches_patterns(text, patterns):
                    return "medium", f"Ввод чувствительных данных ({category})"
            
            return "low", ""
        
        # 4. select_option
        if tool_name == "select_option":
            value = tool_input.get("value", "")
            for category, patterns in self.DANGEROUS_PATTERNS.items():
                if self._matches_patterns(value, patterns):
                    return "medium", f"Выбор опасной опции ({category}): '{value}'"
            return "low", ""
        
        # 5. Базовый риск инструмента
        base_risk = self.TOOL_BASE_RISK.get(tool_name, "low")
        return base_risk, ""
    
    def _matches_patterns(self, text: str, patterns: list) -> bool:
        """Проверяет, соответствует ли текст паттернам."""
        if not text:
            return False
        
        text_lower = text.lower()
        return any(pattern.lower() in text_lower for pattern in patterns)
    
    def _is_dangerous_url(self, url: str) -> bool:
        """Проверяет, является ли URL потенциально опасным."""
        if not url:
            return False
        
        url_lower = url.lower()
        return any(
            re.search(pattern, url_lower)
            for pattern in self.DANGEROUS_URL_PATTERNS
        )
    
    def _get_element_text(
        self,
        tool_input: Dict[str, Any],
        page_context: Dict[str, Any]
    ) -> str:
        """Получает текст элемента по селектору или индексу."""
        # Пробуем получить по индексу
        element_index = tool_input.get("element_index")
        if element_index is not None:
            elements = page_context.get("interactive_elements", [])
            if 0 <= element_index < len(elements):
                element = elements[element_index]
                return element.get("text", "") or element.get("aria-label", "")
        
        # Возвращаем селектор как fallback
        return tool_input.get("selector", "")
    
    def _is_sensitive_field(
        self,
        selector: str,
        page_context: Dict[str, Any]
    ) -> bool:
        """Проверяет, является ли поле чувствительным."""
        if not selector:
            return False
        
        selector_lower = selector.lower()
        sensitive_keywords = [
            "password", "pass", "pwd", "secret",
            "card", "credit", "cvv", "cvc",
            "ssn", "social", "pin"
        ]
        
        return any(kw in selector_lower for kw in sensitive_keywords)
    
    def _format_action_description(
        self,
        action: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        page_context: Dict[str, Any]
    ) -> str:
        """Форматирует описание действия для пользователя."""
        url = page_context.get("url", "")
        
        if tool_name == "navigate":
            return f"Переход на: {tool_input.get('url', 'неизвестно')}"
        
        if tool_name == "click":
            element_text = self._get_element_text(tool_input, page_context)
            selector = tool_input.get("selector", "")
            if element_text:
                return f"Клик на '{element_text}' на странице {url}"
            return f"Клик на {selector} на странице {url}"
        
        if tool_name == "type_text":
            text = tool_input.get("text", "")
            # Скрываем потенциально чувствительные данные
            masked_text = text[:3] + "***" if len(text) > 3 else "***"
            return f"Ввод текста '{masked_text}' на странице {url}"
        
        return f"{tool_name}: {tool_input}"
    
    async def request_confirmation(self, action: str, risk_reason: str) -> bool:
        """
        Запрашивает подтверждение у пользователя.
        
        Args:
            action: Описание действия
            risk_reason: Причина запроса подтверждения
            
        Returns:
            bool: True если подтверждено
        """
        if self._skip_confirmations:
            logger.debug("Автоматическое подтверждение (skip mode)")
            return True
        
        if self._confirmation_callback:
            return await self._confirmation_callback(action, risk_reason)
        
        # Fallback на консольный ввод
        return await self._console_confirmation(action, risk_reason)
    
    async def _console_confirmation(self, action: str, risk_reason: str) -> bool:
        """Запрашивает подтверждение через консоль."""
        print("\n" + "=" * 60)
        print("⚠️  ТРЕБУЕТСЯ ПОДТВЕРЖДЕНИЕ")
        print("=" * 60)
        print(f"\nДействие: {action}")
        print(f"Причина: {risk_reason}")
        print("\nРазрешить это действие? (yes/no): ", end="")
        
        try:
            # Используем asyncio для неблокирующего ввода
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, input)
            return response.lower() in ("yes", "y", "да", "д", "1")
        except Exception as e:
            logger.error(f"Ошибка при запросе подтверждения: {e}")
            return False