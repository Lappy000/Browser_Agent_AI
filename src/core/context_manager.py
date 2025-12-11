"""
ContextManager - управление контекстом и историей действий.

Отвечает за:
- Хранение истории действий агента
- Формирование контекста для LLM
- Оптимизацию размера контекста
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


logger = logging.getLogger(__name__)


@dataclass
class ActionRecord:
    """
    Запись о выполненном действии.
    
    Attributes:
        timestamp: Время выполнения
        tool_name: Имя использованного инструмента
        tool_input: Параметры инструмента
        result: Результат выполнения
        success: Успешность выполнения
        error: Сообщение об ошибке (если есть)
    """
    timestamp: datetime
    tool_name: str
    tool_input: Dict[str, Any]
    result: str
    success: bool = True
    error: Optional[str] = None
    
    def to_summary(self) -> str:
        """
        Возвращает краткое описание действия.
        
        Returns:
            str: Краткое описание в формате "tool_name(params) -> result"
        """
        # Форматируем параметры
        params = []
        for key, value in self.tool_input.items():
            if isinstance(value, str) and len(value) > 30:
                value = value[:30] + "..."
            params.append(f"{key}={repr(value)}")
        params_str = ", ".join(params)
        
        # Форматируем результат
        result_str = self.result
        if len(result_str) > 100:
            result_str = result_str[:100] + "..."
        
        status = "✓" if self.success else "✗"
        
        if self.error:
            return f"{status} {self.tool_name}({params_str}) -> ОШИБКА: {self.error}"
        return f"{status} {self.tool_name}({params_str}) -> {result_str}"


class ContextManager:
    """
    Управление контекстом и историей действий агента.
    
    Хранит историю всех действий агента и предоставляет
    методы для формирования контекста для LLM.
    
    Attributes:
        max_history: Максимальное количество записей в истории
        action_history: Список записей о действиях
        
    Example:
        ```python
        context = ContextManager(max_history=20)
        
        context.add_action(
            tool_name="navigate",
            tool_input={"url": "https://google.com"},
            result="Успешно перешли на страницу",
            success=True
        )
        
        history = context.get_history_summary()
        ```
    """
    
    def __init__(self, max_history: int = 20):
        """
        Инициализирует менеджер контекста.
        
        Args:
            max_history: Максимальное количество записей в истории
        """
        self.max_history = max_history
        self._action_history: List[ActionRecord] = []
        self._page_state_history: List[Dict[str, Any]] = []
        self._messages: List[Dict[str, Any]] = []
        
        logger.debug(f"ContextManager инициализирован: max_history={max_history}")
    
    def add_action(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        result: str,
        success: bool = True,
        error: Optional[str] = None
    ) -> None:
        """
        Добавляет действие в историю.
        
        Args:
            tool_name: Имя инструмента
            tool_input: Параметры инструмента
            result: Результат выполнения
            success: Успешность выполнения
            error: Сообщение об ошибке (если есть)
        """
        record = ActionRecord(
            timestamp=datetime.now(),
            tool_name=tool_name,
            tool_input=tool_input,
            result=result,
            success=success,
            error=error
        )
        
        self._action_history.append(record)
        
        # Обрезаем историю если превышен лимит
        if len(self._action_history) > self.max_history:
            removed = len(self._action_history) - self.max_history
            self._action_history = self._action_history[-self.max_history:]
            logger.debug(f"История обрезана: удалено {removed} записей")
        
        logger.debug(f"Добавлено действие: {record.to_summary()}")
    
    def get_history_summary(self) -> List[str]:
        """
        Возвращает краткую историю действий.
        
        Returns:
            List[str]: Список кратких описаний действий
        """
        return [record.to_summary() for record in self._action_history]
    
    def get_formatted_history(self) -> str:
        """
        Возвращает отформатированную историю для промпта.
        
        Returns:
            str: Форматированная история действий
        """
        if not self._action_history:
            return "История пуста - это первое действие."
        
        summaries = self.get_history_summary()
        lines = [f"{i+1}. {s}" for i, s in enumerate(summaries)]
        
        return "\n".join(lines)
    
    def get_last_actions(self, count: int = 5) -> List[ActionRecord]:
        """
        Возвращает последние N действий.
        
        Args:
            count: Количество действий
            
        Returns:
            List[ActionRecord]: Список последних действий
        """
        return self._action_history[-count:]
    
    def get_last_error(self) -> Optional[ActionRecord]:
        """
        Возвращает последнее неудачное действие.
        
        Returns:
            ActionRecord | None: Последняя ошибка или None
        """
        for record in reversed(self._action_history):
            if not record.success:
                return record
        return None
    
    def add_message(self, message: Dict[str, Any]) -> None:
        """
        Добавляет сообщение в историю диалога с LLM.
        
        Args:
            message: Сообщение в формате Chat API
        """
        self._messages.append(message)
    
    def get_messages(self) -> List[Dict[str, Any]]:
        """
        Возвращает историю сообщений для LLM.
        
        Returns:
            List[Dict]: Список сообщений
        """
        return self._messages.copy()
    
    def add_page_state(self, state: Dict[str, Any]) -> None:
        """
        Сохраняет состояние страницы в истории.
        
        Args:
            state: Словарь с состоянием страницы
        """
        self._page_state_history.append({
            "timestamp": datetime.now().isoformat(),
            "state": state
        })
        
        # Ограничиваем историю состояний
        if len(self._page_state_history) > 10:
            self._page_state_history = self._page_state_history[-10:]
    
    def get_last_page_state(self) -> Optional[Dict[str, Any]]:
        """
        Возвращает последнее сохранённое состояние страницы.
        
        Returns:
            Dict | None: Состояние страницы или None
        """
        if self._page_state_history:
            return self._page_state_history[-1]["state"]
        return None
    
    def get_actions_count(self) -> int:
        """
        Возвращает количество выполненных действий.
        
        Returns:
            int: Количество действий
        """
        return len(self._action_history)
    
    def get_success_rate(self) -> float:
        """
        Возвращает процент успешных действий.
        
        Returns:
            float: Процент успешных действий (0.0 - 1.0)
        """
        if not self._action_history:
            return 1.0
        
        successful = sum(1 for r in self._action_history if r.success)
        return successful / len(self._action_history)
    
    def clear(self) -> None:
        """
        Очищает всю историю.
        
        Используется при начале новой задачи.
        """
        self._action_history.clear()
        self._page_state_history.clear()
        self._messages.clear()
        logger.debug("История очищена")
    
    def clear_messages(self) -> None:
        """
        Очищает только историю сообщений.
        
        Используется для сброса диалога с LLM.
        """
        self._messages.clear()
        logger.debug("История сообщений очищена")
    
    def get_context_summary(self) -> Dict[str, Any]:
        """
        Возвращает сводку текущего контекста.
        
        Returns:
            Dict: Сводка с информацией о контексте
        """
        return {
            "actions_count": len(self._action_history),
            "messages_count": len(self._messages),
            "page_states_count": len(self._page_state_history),
            "success_rate": self.get_success_rate(),
            "last_action": (
                self._action_history[-1].to_summary() 
                if self._action_history else None
            ),
            "last_error": (
                self.get_last_error().error 
                if self.get_last_error() else None
            )
        }