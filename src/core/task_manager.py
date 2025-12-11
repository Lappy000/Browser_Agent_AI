"""
TaskManager - управление задачами агента.

Отвечает за:
- Отслеживание статуса текущей задачи
- Управление жизненным циклом задачи
- Хранение результатов выполнения
"""

import logging
from typing import Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """
    Статус выполнения задачи.
    
    Values:
        IDLE: Нет активной задачи
        RUNNING: Задача выполняется
        WAITING_INPUT: Ожидание ввода от пользователя
        COMPLETED: Задача успешно завершена
        FAILED: Задача не удалась
        CANCELLED: Задача отменена
    """
    IDLE = "idle"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskResult:
    """
    Результат выполнения задачи.
    
    Attributes:
        success: Была ли задача выполнена успешно
        summary: Краткое описание результата
        status: Статус задачи
        data: Извлечённые данные (если есть)
        error: Сообщение об ошибке (если есть)
        actions_count: Количество выполненных действий
        duration_seconds: Длительность выполнения в секундах
    """
    success: bool
    summary: str
    status: TaskStatus
    data: Optional[str] = None
    error: Optional[str] = None
    actions_count: int = 0
    duration_seconds: float = 0.0


@dataclass
class Task:
    """
    Представляет задачу агента.
    
    Attributes:
        id: Уникальный идентификатор задачи
        description: Описание задачи от пользователя
        status: Текущий статус задачи
        created_at: Время создания
        started_at: Время начала выполнения
        completed_at: Время завершения
        result: Результат выполнения
        pending_question: Вопрос к пользователю (если status == WAITING_INPUT)
    """
    id: str
    description: str
    status: TaskStatus = TaskStatus.IDLE
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[TaskResult] = None
    pending_question: Optional[str] = None
    
    def get_duration(self) -> float:
        """
        Возвращает длительность выполнения задачи.
        
        Returns:
            float: Длительность в секундах
        """
        if not self.started_at:
            return 0.0
        
        end_time = self.completed_at or datetime.now()
        return (end_time - self.started_at).total_seconds()


class TaskManager:
    """
    Управление задачами агента.
    
    Отслеживает текущую задачу, историю задач и
    предоставляет методы для управления жизненным циклом.
    
    Attributes:
        current_task: Текущая активная задача
        task_history: История выполненных задач
        max_iterations: Максимальное количество итераций для одной задачи
        
    Example:
        ```python
        manager = TaskManager(max_iterations=50)
        
        manager.set_task("Найди на google.com информацию о погоде")
        manager.start()
        
        # ... выполнение ...
        
        manager.complete("Найдена информация о погоде: +20°C")
        result = manager.get_result()
        ```
    """
    
    def __init__(self, max_iterations: int = 50):
        """
        Инициализирует менеджер задач.
        
        Args:
            max_iterations: Максимальное количество итераций
        """
        self.max_iterations = max_iterations
        self._current_task: Optional[Task] = None
        self._task_history: List[Task] = []
        self._iteration_count: int = 0
        self._task_counter: int = 0
        
        logger.debug(f"TaskManager инициализирован: max_iterations={max_iterations}")
    
    @property
    def current_task(self) -> Optional[Task]:
        """Возвращает текущую задачу."""
        return self._current_task
    
    @property
    def status(self) -> TaskStatus:
        """Возвращает статус текущей задачи."""
        if self._current_task is None:
            return TaskStatus.IDLE
        return self._current_task.status
    
    @property
    def is_running(self) -> bool:
        """Проверяет, выполняется ли задача."""
        return self.status == TaskStatus.RUNNING
    
    @property
    def is_waiting_input(self) -> bool:
        """Проверяет, ожидается ли ввод пользователя."""
        return self.status == TaskStatus.WAITING_INPUT
    
    @property
    def is_complete(self) -> bool:
        """Проверяет, завершена ли задача."""
        return self.status in (
            TaskStatus.COMPLETED, 
            TaskStatus.FAILED, 
            TaskStatus.CANCELLED
        )
    
    @property
    def iteration_count(self) -> int:
        """Возвращает количество итераций текущей задачи."""
        return self._iteration_count
    
    def set_task(self, description: str) -> Task:
        """
        Устанавливает новую задачу.
        
        Args:
            description: Описание задачи от пользователя
            
        Returns:
            Task: Созданная задача
            
        Raises:
            RuntimeError: Если уже есть активная задача
        """
        if self._current_task and not self.is_complete:
            raise RuntimeError(
                "Уже есть активная задача. Завершите её перед созданием новой."
            )
        
        self._task_counter += 1
        task_id = f"task_{self._task_counter}_{datetime.now().strftime('%H%M%S')}"
        
        task = Task(
            id=task_id,
            description=description,
            status=TaskStatus.IDLE
        )
        
        self._current_task = task
        self._iteration_count = 0
        
        logger.info(f"Создана задача: {task_id} - {description[:50]}...")
        return task
    
    def start(self) -> None:
        """
        Начинает выполнение задачи.
        
        Raises:
            RuntimeError: Если нет текущей задачи
        """
        if not self._current_task:
            raise RuntimeError("Нет задачи для выполнения")
        
        self._current_task.status = TaskStatus.RUNNING
        self._current_task.started_at = datetime.now()
        
        logger.info(f"Задача начата: {self._current_task.id}")
    
    def increment_iteration(self) -> bool:
        """
        Увеличивает счётчик итераций.
        
        Returns:
            bool: True если можно продолжать, False если достигнут лимит
        """
        self._iteration_count += 1
        
        if self._iteration_count >= self.max_iterations:
            logger.warning(
                f"Достигнут лимит итераций: {self._iteration_count}"
            )
            return False
        
        return True
    
    def complete(self, summary: str, data: Optional[str] = None) -> TaskResult:
        """
        Отмечает задачу как успешно выполненную.
        
        Args:
            summary: Краткое описание результата
            data: Извлечённые данные (опционально)
            
        Returns:
            TaskResult: Результат выполнения
            
        Raises:
            RuntimeError: Если нет активной задачи
        """
        if not self._current_task:
            raise RuntimeError("Нет активной задачи")
        
        self._current_task.status = TaskStatus.COMPLETED
        self._current_task.completed_at = datetime.now()
        
        result = TaskResult(
            success=True,
            summary=summary,
            status=TaskStatus.COMPLETED,
            data=data,
            actions_count=self._iteration_count,
            duration_seconds=self._current_task.get_duration()
        )
        
        self._current_task.result = result
        self._task_history.append(self._current_task)
        
        logger.info(
            f"Задача завершена: {self._current_task.id} - {summary[:50]}..."
        )
        
        return result
    
    def fail(self, reason: str) -> TaskResult:
        """
        Отмечает задачу как неудачную.
        
        Args:
            reason: Причина неудачи
            
        Returns:
            TaskResult: Результат с ошибкой
            
        Raises:
            RuntimeError: Если нет активной задачи
        """
        if not self._current_task:
            raise RuntimeError("Нет активной задачи")
        
        self._current_task.status = TaskStatus.FAILED
        self._current_task.completed_at = datetime.now()
        
        result = TaskResult(
            success=False,
            summary=f"Задача не выполнена: {reason}",
            status=TaskStatus.FAILED,
            error=reason,
            actions_count=self._iteration_count,
            duration_seconds=self._current_task.get_duration()
        )
        
        self._current_task.result = result
        self._task_history.append(self._current_task)
        
        logger.warning(f"Задача не удалась: {self._current_task.id} - {reason}")
        
        return result
    
    def cancel(self) -> TaskResult:
        """
        Отменяет текущую задачу.
        
        Returns:
            TaskResult: Результат с отметкой об отмене
        """
        if not self._current_task:
            raise RuntimeError("Нет активной задачи")
        
        self._current_task.status = TaskStatus.CANCELLED
        self._current_task.completed_at = datetime.now()
        
        result = TaskResult(
            success=False,
            summary="Задача отменена пользователем",
            status=TaskStatus.CANCELLED,
            actions_count=self._iteration_count,
            duration_seconds=self._current_task.get_duration()
        )
        
        self._current_task.result = result
        self._task_history.append(self._current_task)
        
        logger.info(f"Задача отменена: {self._current_task.id}")
        
        return result
    
    def wait_for_input(self, question: str) -> None:
        """
        Переводит задачу в режим ожидания ввода.
        
        Args:
            question: Вопрос к пользователю
        """
        if not self._current_task:
            raise RuntimeError("Нет активной задачи")
        
        self._current_task.status = TaskStatus.WAITING_INPUT
        self._current_task.pending_question = question
        
        logger.info(f"Ожидание ввода: {question[:50]}...")
    
    def resume_with_input(self, user_input: str) -> str:
        """
        Продолжает выполнение с ответом пользователя.
        
        Args:
            user_input: Ответ пользователя
            
        Returns:
            str: Ответ пользователя для передачи в LLM
        """
        if not self._current_task:
            raise RuntimeError("Нет активной задачи")
        
        if self._current_task.status != TaskStatus.WAITING_INPUT:
            raise RuntimeError("Задача не ожидает ввода")
        
        self._current_task.status = TaskStatus.RUNNING
        self._current_task.pending_question = None
        
        logger.info(f"Получен ввод пользователя: {user_input[:50]}...")
        
        return user_input
    
    def get_result(self) -> Optional[TaskResult]:
        """
        Возвращает результат текущей задачи.
        
        Returns:
            TaskResult | None: Результат или None если задача не завершена
        """
        if self._current_task:
            return self._current_task.result
        return None
    
    def get_pending_question(self) -> Optional[str]:
        """
        Возвращает вопрос, ожидающий ответа пользователя.
        
        Returns:
            str | None: Вопрос или None
        """
        if self._current_task:
            return self._current_task.pending_question
        return None
    
    def get_task_history(self) -> List[Task]:
        """
        Возвращает историю выполненных задач.
        
        Returns:
            List[Task]: Список задач
        """
        return self._task_history.copy()
    
    def get_stats(self) -> dict:
        """
        Возвращает статистику по задачам.
        
        Returns:
            dict: Статистика
        """
        completed = sum(
            1 for t in self._task_history 
            if t.status == TaskStatus.COMPLETED
        )
        failed = sum(
            1 for t in self._task_history 
            if t.status == TaskStatus.FAILED
        )
        
        return {
            "total_tasks": len(self._task_history),
            "completed": completed,
            "failed": failed,
            "success_rate": completed / len(self._task_history) if self._task_history else 0.0,
            "current_status": self.status.value,
            "current_iterations": self._iteration_count
        }