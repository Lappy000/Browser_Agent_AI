"""
BrowserAgent - главный класс AI-агента для браузерной автоматизации.

Объединяет все компоненты:
- BrowserController для управления браузером
- PageAnalyzer для анализа страниц
- LLMClient для взаимодействия с Claude
- TaskManager для управления задачами
- ContextManager для истории и контекста
- SecurityLayer для проверки опасных действий
"""

import logging
import asyncio
import time
import json
from typing import Optional, Dict, Any, List, Callable, Awaitable, TYPE_CHECKING

from ..browser.controller import BrowserController, BrowserError
from ..browser.page_analyzer import PageAnalyzer
from ..ai.llm_client import LLMClient, LLMResponse, ToolCall, LLMClientError
from ..ai.tools import BROWSER_TOOLS, SCROLL_AMOUNTS
from ..ai.prompts import SYSTEM_PROMPT, build_task_prompt
from ..ai.prompts_compact import SYSTEM_PROMPT_COMPACT, build_task_prompt_compact
from ..config import get_config
from ..constants import Limits, LoopDetection, Timeouts
from .task_manager import TaskManager, TaskStatus, TaskResult
from .context_manager import ContextManager

if TYPE_CHECKING:
    from ..security.security_layer import SecurityLayer


logger = logging.getLogger(__name__)


class AgentError(Exception):
    """Базовое исключение для ошибок агента."""
    pass


class BrowserAgent:
    """
    Главный класс AI-агента для автоматизации браузера.
    
    Реализует главный цикл агента:
    1. Получить текущее состояние страницы
    2. Отправить в LLM с историей и инструментами
    3. Выполнить действие из ответа
    4. Повторять пока задача не выполнена
    
    Attributes:
        browser_controller: Контроллер браузера
        page_analyzer: Анализатор страниц
        llm_client: Клиент для Claude API
        task_manager: Менеджер задач
        context_manager: Менеджер контекста
        
    Example:
        ```python
        agent = BrowserAgent(api_key="sk-ant-...")
        
        await agent.start()
        result = await agent.run("Перейди на google.com и найди погоду в Москве")
        await agent.stop()
        
        print(result.summary)
        ```
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_iterations: Optional[int] = None,
        on_action: Optional[Callable[[str, Dict], Awaitable[None]]] = None,
        on_status: Optional[Callable[[str], Awaitable[None]]] = None,
        security_layer: Optional["SecurityLayer"] = None
    ):
        """
        Инициализирует агента.
        
        Args:
            api_key: API ключ Anthropic (или из конфига)
            model: Модель Claude (или из конфига)
            max_iterations: Максимум итераций (или из конфига)
            on_action: Callback при выполнении действия
            on_status: Callback при изменении статуса
            security_layer: Слой безопасности для проверки действий
        """
        config = get_config()
        
        # Определяем провайдера и настройки
        provider = config.ai_provider
        self._base_url = None
        
        if provider == "openrouter":
            self._api_key = api_key or config.openrouter_api_key
            self._model = model or config.openrouter_model
        elif provider == "custom":
            self._api_key = api_key or config.custom_api_key
            self._model = model or config.llm_model
            self._base_url = config.custom_api_base_url
        else:
            self._api_key = api_key or config.anthropic_api_key
            self._model = model or config.anthropic_model
        
        self._max_iterations = max_iterations or config.max_iterations
        
        if not self._api_key:
            raise AgentError(
                f"API ключ {provider.upper()} не указан. "
                f"Установите {provider.upper()}_API_KEY в .env или передайте в конструктор."
            )
        
        if provider == "custom" and not self._base_url:
            raise AgentError(
                "CUSTOM_API_BASE_URL не указан для провайдера 'custom'. "
                "Установите CUSTOM_API_BASE_URL в .env"
            )
        
        # Инициализируем компоненты
        self.browser_controller = BrowserController()
        
        # Параметры PageAnalyzer - используем константы
        self.page_analyzer = PageAnalyzer(
            max_dom_size=Limits.MAX_DOM_SIZE,
            max_elements=Limits.MAX_ELEMENTS
        )
        
        # Используем компактные промпты для экономии токенов
        self._use_compact_prompts = getattr(config, 'use_compact_prompts', True)
        self.llm_client = LLMClient(
            api_key=self._api_key,
            model=self._model,
            provider=provider,
            base_url=self._base_url
        )
        self.task_manager = TaskManager(max_iterations=self._max_iterations)
        self.context_manager = ContextManager(max_history=Limits.MAX_HISTORY)
        
        # Security Layer - может быть отключен через конфиг
        if config.security_enabled and security_layer:
            self.security_layer = security_layer
        elif config.security_enabled and not security_layer:
            # Если включен в конфиге но не передан - используем дефолтный
            logger.info("Security Layer включен в конфиге, используется с auto-approve")
            self.security_layer = None  # будет проверяться в execute_tool
        else:
            logger.info("Security Layer отключен в конфиге")
            self.security_layer = None
        
        # Callbacks
        self._on_action = on_action
        self._on_status = on_status
        
        # Automatic data capture for extraction tasks
        # Stores extracted data to prevent loss during complete_task call
        self._extracted_data: Optional[str] = None
        
        # Token usage tracking
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost = 0.0
        
        # Vision mode state tracking (for frequency control)
        self._last_navigation_url: Optional[str] = None
        self._last_action_failed: bool = False
        
        # Task memory and reflection tracking
        self._original_task: str = ""           # Store original task for reflection
        self._action_count: int = 0             # Count actions taken
        self._actions_taken: List[str] = []     # List of actions for reflection
        
        self._is_started = False
        
        logger.info(f"BrowserAgent инициализирован: model={self._model}, vision={config.vision.enabled}")
    
    async def start(self) -> None:
        """
        Запускает агента и браузер.
        
        Должен быть вызван перед выполнением задач.
        """
        if self._is_started:
            logger.warning("Агент уже запущен")
            return
        
        logger.info("Запуск агента...")
        await self.browser_controller.launch()
        self._is_started = True
        
        await self._notify_status("Агент запущен")
        logger.info("Агент успешно запущен")
    
    async def stop(self) -> None:
        """
        Останавливает агента и закрывает браузер.
        """
        if not self._is_started:
            return
        
        logger.info("Остановка агента...")
        
        await self.browser_controller.close()
        await self.llm_client.close()
        
        self._is_started = False
        await self._notify_status("Агент остановлен")
        
        # Выводим итоговую статистику токенов
        if self._total_input_tokens > 0 or self._total_output_tokens > 0:
            logger.info("=" * 50)
            logger.info("📊 Итоговая статистика токенов:")
            logger.info(f"   Input tokens:  {self._total_input_tokens:,}")
            logger.info(f"   Output tokens: {self._total_output_tokens:,}")
            logger.info(f"   Total tokens:  {self._total_input_tokens + self._total_output_tokens:,}")
            logger.info(f"   Estimated cost: ${self._total_cost:.4f}")
            logger.info("=" * 50)
        
        logger.info("Агент остановлен")
    
    def get_token_stats(self) -> Dict[str, Any]:
        """
        Получает статистику использования токенов.
        
        Returns:
            Dict: Статистика с ключами input_tokens, output_tokens, total_tokens, cost
        """
        return {
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens,
            "estimated_cost": self._total_cost
        }
    
    async def run(self, task: str, user_response_callback: Optional[Callable[[str], Awaitable[str]]] = None) -> TaskResult:
        """
        Выполняет задачу.
        
        Args:
            task: Описание задачи от пользователя
            user_response_callback: Async callback для получения ответа пользователя на ask_user.
                                   Принимает question (str), возвращает ответ (str).
                                   Если не указан, ask_user будет возвращать сообщение об ожидании.
            
        Returns:
            TaskResult: Результат выполнения
            
        Raises:
            AgentError: Если агент не запущен
        """
        config = get_config()
        
        # Константы для предотвращения бесконечных циклов (из constants.py)
        MAX_ITERATIONS = config.max_iterations or Limits.MAX_ITERATIONS
        TASK_TIMEOUT_SECONDS = config.task_timeout or Limits.TASK_TIMEOUT_SECONDS
        
        if not self._is_started:
            raise AgentError("Агент не запущен. Вызовите start() перед run().")
        
        # Ensure valid page before starting task
        if not await self._ensure_valid_page():
            return TaskResult(
                success=False,
                message="Не удалось установить соединение с браузером",
                status=TaskStatus.FAILED
            )
        
        # Подготавливаем задачу
        self.context_manager.clear()
        self.task_manager.set_task(task)
        self.task_manager.start()
        
        # Reset task memory for new task
        self._original_task = task
        self._action_count = 0
        self._actions_taken = []
        
        await self._notify_status(f"Начало задачи: {task[:50]}...")
        
        # Инициализируем историю сообщений с SLIDING WINDOW для экономии токенов
        MAX_MESSAGE_HISTORY = Limits.MAX_MESSAGE_HISTORY
        messages = []
        
        # Инициализируем счетчики для механизмов завершения
        start_time = time.time()
        iteration = 0
        
        # ==== LOOP DETECTION: отслеживание повторяющихся действий ====
        recent_actions: list[str] = []
        MAX_REPEATED_ACTIONS = LoopDetection.MAX_REPEATED_ACTIONS
        
        # Callback для ответов пользователя
        self._user_response_callback = user_response_callback
        
        try:
            # Главный цикл агента - теперь также проверяем WAITING_INPUT
            while (self.task_manager.is_running or self.task_manager.is_waiting_input) and iteration < MAX_ITERATIONS:
                iteration += 1
                
                # Механизм 1: Проверяем лимит итераций
                if iteration >= MAX_ITERATIONS:
                    logger.warning(f"Достигнут максимум итераций ({MAX_ITERATIONS})")
                    return self.task_manager.complete(
                        f"Задача прервана: достигнут лимит итераций ({iteration} итераций)"
                    )
                
                # Механизм 2: Проверяем таймаут
                elapsed_time = time.time() - start_time
                if elapsed_time > TASK_TIMEOUT_SECONDS:
                    logger.warning(f"Таймаут задачи после {elapsed_time:.1f}s")
                    return self.task_manager.complete(
                        f"Задача прервана по таймауту после {int(elapsed_time)}s ({iteration} итераций)"
                    )
                
                logger.debug(f"Итерация {iteration} (прошло {elapsed_time:.1f}s)")
                
                # Обновляем счетчик в task_manager для совместимости
                if not self.task_manager.increment_iteration():
                    return self.task_manager.fail(
                        f"Превышен лимит итераций ({self._max_iterations})"
                    )
                
                # Получаем состояние страницы (с опциональным скриншотом)
                page_state = await self.get_page_context()
                self.context_manager.add_page_state(page_state)
                
                # Формируем текстовое сообщение для LLM (компактная или полная версия)
                if self._use_compact_prompts:
                    prompt_text = build_task_prompt_compact(
                        task=self._original_task,  # Always use original task for task memory
                        url=page_state["url"],
                        title=page_state["title"],
                        interactive_elements=page_state["interactive_elements"],
                        content=page_state["text_content"],
                        action_history=self.context_manager.get_history_summary(),
                        iteration=iteration,
                        max_iterations=MAX_ITERATIONS,
                        actions_taken=self._actions_taken
                    )
                    system_prompt = SYSTEM_PROMPT_COMPACT
                else:
                    prompt_text = build_task_prompt(
                        task=task,
                        url=page_state["url"],
                        title=page_state["title"],
                        interactive_elements=page_state["interactive_elements"],
                        content=page_state["text_content"],
                        action_history=self.context_manager.get_history_summary()
                    )
                    system_prompt = SYSTEM_PROMPT
                
                # Создаем сообщение с опциональным скриншотом для vision режима
                screenshot_b64 = page_state.get("screenshot_b64")
                user_message = self._build_user_message_with_vision(prompt_text, screenshot_b64)
                
                # Добавляем новое сообщение
                messages.append(user_message)
                
                # КРИТИЧЕСКАЯ ОПТИМИЗАЦИЯ: Очищаем старую историю (sliding window)
                # FIX: Используем безопасную обрезку, сохраняющую пары tool_use/tool_result
                if len(messages) > MAX_MESSAGE_HISTORY:
                    messages = self._safe_trim_messages(messages, MAX_MESSAGE_HISTORY)
                    logger.debug(f"История сообщений сокращена до {len(messages)} (экономия токенов)")
                
                # Отправляем в LLM с правильным system_prompt
                try:
                    # Show thinking indicator if enabled
                    if config.show_thinking:
                        print("🤔 Думаю...")
                        logger.info("Waiting for LLM response...")
                    
                    response = await self.llm_client.send_message(
                        messages=messages,
                        tools=BROWSER_TOOLS,
                        system_prompt=system_prompt
                    )
                    
                    # Display LLM's reasoning/thinking text if enabled
                    if config.show_thinking and response.content:
                        print("=" * 50)
                        print("💭 Размышления агента:")
                        print(response.content)
                        print("=" * 50)
                    
                    # Track token usage
                    if response.usage:
                        input_tokens = response.usage.get("input_tokens", 0)
                        output_tokens = response.usage.get("output_tokens", 0)
                        self._total_input_tokens += input_tokens
                        self._total_output_tokens += output_tokens
                        
                        # Calculate cost (approximate for Claude Sonnet 4)
                        # Input: $3 per 1M tokens, Output: $15 per 1M tokens
                        input_cost = (input_tokens / 1_000_000) * 3.0
                        output_cost = (output_tokens / 1_000_000) * 15.0
                        iteration_cost = input_cost + output_cost
                        self._total_cost += iteration_cost
                        
                        logger.debug(
                            f"Iteration {iteration}: "
                            f"input={input_tokens}, output={output_tokens}, "
                            f"cost=${iteration_cost:.4f}, total=${self._total_cost:.4f}"
                        )
                        
                        # COST CONTROL: Проверяем лимиты стоимости
                        if self._total_cost >= config.max_cost_per_task:
                            logger.warning(
                                f"💰 COST LIMIT REACHED: ${self._total_cost:.4f} >= "
                                f"${config.max_cost_per_task:.2f}"
                            )
                            print(f"\n⚠️ ЛИМИТ СТОИМОСТИ ДОСТИГНУТ: ${self._total_cost:.4f}")
                            return self.task_manager.complete(
                                f"Задача прервана: достигнут лимит стоимости "
                                f"(${self._total_cost:.4f} >= ${config.max_cost_per_task:.2f})"
                            )
                        
                        # Предупреждение о приближении к лимиту
                        if (self._total_cost >= config.warn_cost_threshold and
                            not getattr(self, '_cost_warning_shown', False)):
                            self._cost_warning_shown = True
                            logger.warning(
                                f"💰 Cost warning: ${self._total_cost:.4f} >= "
                                f"${config.warn_cost_threshold:.2f} threshold"
                            )
                            print(f"\n⚠️ ВНИМАНИЕ: Стоимость задачи ${self._total_cost:.4f} "
                                  f"(порог ${config.warn_cost_threshold:.2f})")
                
                except LLMClientError as e:
                    logger.error(f"Ошибка LLM: {e}")
                    return self.task_manager.fail(f"Ошибка LLM: {e}")
                
                # Обрабатываем ответ
                if response.tool_calls:
                    # Добавляем ответ assistant в историю
                    assistant_msg = self.llm_client.build_assistant_tool_use_message(
                        response.tool_calls,
                        response.content
                    )
                    messages.append(assistant_msg)
                    
                    # Выполняем tool calls и собираем результаты
                    # FIX: Для Anthropic API все tool_result должны быть в ОДНОМ user message
                    tool_results: List[Dict[str, Any]] = []
                    ask_user_data: Optional[Dict[str, str]] = None  # {question, answer}
                    task_completion_input: Optional[Dict[str, Any]] = None
                    
                    for tool_call in response.tool_calls:
                        # ==== LOOP DETECTION: записываем действие ====
                        action_key = self._get_action_key(tool_call.name, tool_call.input)
                        recent_actions.append(action_key)
                        
                        # Проверяем на зацикливание
                        loop_detected, loop_message = self._check_loop_detection(recent_actions, MAX_REPEATED_ACTIONS)
                        if loop_detected:
                            logger.warning(f"🔄 LOOP DETECTED: {loop_message}")
                            # Собираем результат ошибки зацикливания
                            tool_results.append({
                                "tool_call_id": tool_call.id,
                                "result": f"⚠️ ЗАЦИКЛИВАНИЕ ОБНАРУЖЕНО: {loop_message}\n\n"
                                       f"Ты повторяешь одно и то же действие ({action_key}) {MAX_REPEATED_ACTIONS}+ раз подряд.\n"
                                       f"ПОПРОБУЙ ДРУГОЙ ПОДХОД или заверши задачу через complete_task.\n"
                                       f"Варианты: 1) Используй другой селектор/метод 2) scroll() для загрузки контента "
                                       f"3) complete_task если данные уже есть",
                                "is_error": True
                            })
                            
                            # Очищаем историю для нового шанса
                            recent_actions.clear()
                            continue  # Пропускаем выполнение, даем LLM переосмыслить
                        
                        result = await self.execute_tool(
                            tool_call.name,
                            tool_call.input
                        )
                        
                        # Track action for reflection
                        self._action_count += 1
                        action_desc = self._format_action_for_reflection(tool_call.name, tool_call.input)
                        self._actions_taken.append(action_desc)
                        
                        # Собираем результат (не добавляем в messages пока)
                        tool_results.append({
                            "tool_call_id": tool_call.id,
                            "result": result["message"],
                            "is_error": not result["success"]
                        })
                        
                        # Механизм 3: Проверяем попытку завершения задачи
                        if tool_call.name in ("complete_task", "attempt_completion"):
                            logger.info(f"Задача завершена агентом через {tool_call.name}")
                            task_completion_input = tool_call.input
                            # Продолжаем собирать результаты других tools, но отметим завершение
                        
                        # ==== FIX ask_user: собираем данные для ответа пользователя ====
                        if tool_call.name == "ask_user":
                            question = tool_call.input.get("question", "")
                            user_answer = await self._handle_ask_user(question)
                            
                            if user_answer:
                                ask_user_data = {"question": question, "answer": user_answer}
                                # Возвращаем task в running после получения ответа
                                if self.task_manager.is_waiting_input:
                                    self.task_manager.resume_with_input(user_answer)
                    
                    # FIX: Добавляем ВСЕ tool_results в ОДНО сообщение (или несколько для OpenAI)
                    if tool_results:
                        combined_tool_result_msg = self._build_combined_tool_result_message(tool_results)
                        
                        # Обработка специального случая для OpenRouter/Custom с множественными результатами
                        if isinstance(combined_tool_result_msg, dict) and combined_tool_result_msg.get("_multiple_tool_results"):
                            # Добавляем каждый tool result как отдельное сообщение (OpenAI format)
                            for tr_msg in combined_tool_result_msg["results"]:
                                messages.append(tr_msg)
                        else:
                            messages.append(combined_tool_result_msg)
                    
                    # ПОСЛЕ tool_results добавляем ответ пользователя (если был ask_user)
                    if ask_user_data:
                        messages.append({
                            "role": "user",
                            "content": f"Ответ пользователя на вопрос '{ask_user_data['question']}':\n{ask_user_data['answer']}"
                        })
                    
                    # Обрабатываем завершение задачи после добавления всех сообщений
                    if task_completion_input is not None:
                        return self._handle_task_completion(task_completion_input)
                    
                    # Проверяем статус после всех действий
                    if self.task_manager.is_complete:
                        pass  # Выйдем из while на следующей итерации
                else:
                    # Нет tool calls - добавляем текст и продолжаем
                    if response.content:
                        messages.append({
                            "role": "assistant",
                            "content": response.content
                        })
                        logger.warning(f"LLM вернул текст без tool call: {response.content[:100]}")
                
                # NO pause between iterations for maximum speed
                # await asyncio.sleep(0) - removed entirely for optimal performance
            
            # Если вышли из цикла по достижению MAX_ITERATIONS
            if iteration >= MAX_ITERATIONS:
                logger.warning(f"Максимум итераций ({MAX_ITERATIONS}) достигнут")
                return self.task_manager.complete(
                    f"Задача прервана после {MAX_ITERATIONS} итераций"
                )
            
            # Если вышли из цикла без результата
            if not self.task_manager.is_complete:
                return self.task_manager.fail("Задача не завершена")
            
            return self.task_manager.get_result()
            
        except Exception as e:
            logger.exception(f"Ошибка выполнения задачи: {e}")
            return self.task_manager.fail(str(e))
    
    async def get_page_context(self) -> Dict[str, Any]:
        """
        Получает текущий контекст страницы для LLM.
        
        Включает скриншот если vision режим активен и условия частоты выполнены.
        Оптимизировано для экономии токенов с JPEG сжатием.
        
        Returns:
            Dict: Состояние страницы (с опциональным screenshot_b64)
        """
        config = get_config()
        page = self.browser_controller.page
        
        if not page:
            return {
                "url": "about:blank",
                "title": "",
                "interactive_elements": [],
                "text_content": "",
                "viewport": {"width": 0, "height": 0},
                "screenshot_b64": None
            }
        
        # Определяем нужен ли скриншот на основе vision config
        include_screenshot = self._should_include_screenshot(config, page.url)
        
        # Получаем состояние с оптимизированными настройками скриншота
        state = await self.page_analyzer.get_page_state(
            page,
            include_screenshot=include_screenshot,
            full_page=config.vision.full_page
        )
        
        # Если скриншот включен, захватываем с оптимизацией
        if include_screenshot and state.get("screenshot_b64") is None:
            # Используем оптимизированный захват с JPEG и resize
            state["screenshot_b64"] = await self.page_analyzer._safe_capture_screenshot(
                page,
                full_page=config.vision.full_page,
                use_jpeg=config.vision.use_jpeg,
                jpeg_quality=config.vision.jpeg_quality,
                max_width=config.vision.max_width,
                max_height=config.vision.max_height
            )
        
        return state
    
    async def _ensure_valid_page(self) -> bool:
        """
        Ensure we have a valid page reference. Create new tab if needed.
        
        This method checks if the current page is still valid (not closed)
        and creates a new tab if necessary. Essential for handling cases
        where previous task's page was closed or became stale.
        
        Returns:
            bool: True if we have a valid page, False if recovery failed
        """
        try:
            page = self.browser_controller._page
            
            # Check if current page is None or closed
            if page is None or page.is_closed():
                logger.info("Current page invalid, creating new tab")
                await self.browser_controller.new_tab()
                return True
            
            # Try a simple operation to verify page works
            await page.title()
            return True
            
        except Exception as e:
            logger.warning(f"Page verification failed: {e}, creating new tab")
            try:
                await self.browser_controller.new_tab()
                return True
            except Exception as recovery_error:
                logger.error(f"Failed to recover with new tab: {recovery_error}")
                return False
    
    def _should_include_screenshot(self, config, current_url: str) -> bool:
        """
        Определяет нужно ли включать скриншот на основе настроек vision.
        
        Args:
            config: Конфигурация приложения
            current_url: Текущий URL страницы
            
        Returns:
            bool: True если нужен скриншот
        """
        if not config.vision.enabled:
            return False
        
        frequency = config.vision.frequency
        
        if frequency == "always":
            return True
        
        if frequency == "on_navigation":
            # Скриншот только если URL изменился
            url_changed = self._last_navigation_url != current_url
            self._last_navigation_url = current_url
            return url_changed
        
        if frequency == "on_error":
            # Скриншот только если предыдущее действие failed
            should_capture = self._last_action_failed
            self._last_action_failed = False  # Reset flag
            return should_capture
        
        return False
    
    def _build_user_message_with_vision(
        self,
        text: str,
        screenshot_b64: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Создает user message с опциональным изображением для vision режима.
        
        Поддерживает форматы:
        - Anthropic (Claude): image block с base64 source
        - OpenRouter: может использовать OpenAI-совместимый формат
        
        Args:
            text: Текст сообщения
            screenshot_b64: Base64-encoded PNG скриншот (или None)
            
        Returns:
            Dict: Сообщение в формате для messages API
        """
        config = get_config()
        
        # Если скриншот отсутствует или vision отключен - обычное текстовое сообщение
        if not screenshot_b64 or not config.vision.enabled:
            return {"role": "user", "content": text}
        
        # Vision сообщение с изображением
        # Формат зависит от провайдера
        provider = config.ai_provider
        
        if provider == "anthropic":
            # Anthropic Claude format
            return {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64
                        }
                    },
                    {
                        "type": "text",
                        "text": text
                    }
                ]
            }
        
        elif provider in ("openrouter", "custom"):
            # OpenRouter/OpenAI-compatible format
            # OpenRouter поддерживает оба формата, используем OpenAI-style
            return {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": text
                    }
                ]
            }
        
        else:
            # Fallback - текст без изображения
            logger.warning(f"Unknown provider '{provider}' for vision mode, using text-only")
            return {"role": "user", "content": text}
    
    async def execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Выполняет инструмент и возвращает результат.
        
        Перед выполнением проверяет действие через SecurityLayer
        (если он установлен) и запрашивает подтверждение для
        опасных операций.
        
        Args:
            tool_name: Имя инструмента
            tool_input: Параметры инструмента
            
        Returns:
            Dict: Результат с ключами success, message
        """
        logger.info(f"Выполнение инструмента: {tool_name}({tool_input})")
        
        # Проверяем через SecurityLayer если он установлен
        if self.security_layer:
            page_context = await self.get_page_context()
            action_desc = self._format_action_description(tool_name, tool_input)
            
            allowed, reason = await self.security_layer.check_action(
                action=action_desc,
                tool_name=tool_name,
                tool_input=tool_input,
                page_context=page_context
            )
            
            if not allowed:
                logger.warning(f"Действие заблокировано SecurityLayer: {reason}")
                return {
                    "success": False,
                    "message": f"Действие отклонено: {reason}"
                }
        
        await self._notify_action(tool_name, tool_input)
        
        try:
            result = await self._execute_tool_impl(tool_name, tool_input)
            
            # Log tool call based on current mode (compact/verbose)
            self._log_tool_call(tool_name, tool_input, result)
            
            # Записываем в историю
            # Track action success for vision frequency "on_error"
            self._last_action_failed = not result["success"]
            
            self.context_manager.add_action(
                tool_name=tool_name,
                tool_input=tool_input,
                result=result["message"],
                success=result["success"]
            )
            
            return result
            
        except Exception as e:
            error_msg = f"Ошибка: {e}"
            logger.error(f"Ошибка инструмента {tool_name}: {e}")
            
            self.context_manager.add_action(
                tool_name=tool_name,
                tool_input=tool_input,
                result=error_msg,
                success=False,
                error=str(e)
            )
            
            return {"success": False, "message": error_msg}
    
    def _format_action_description(
        self,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> str:
        """
        Форматирует описание действия для SecurityLayer.
        
        Args:
            tool_name: Имя инструмента
            tool_input: Параметры
            
        Returns:
            str: Человекочитаемое описание
        """
        match tool_name:
            case "navigate":
                return f"Переход на {tool_input.get('url', 'неизвестно')}"
            case "click":
                selector = tool_input.get("selector", "")
                element_idx = tool_input.get("element_index", "")
                target = selector or f"элемент #{element_idx}"
                return f"Клик на {target}"
            case "type_text":
                text = tool_input.get("text", "")
                preview = text[:20] + "..." if len(text) > 20 else text
                return f"Ввод текста: \"{preview}\""
            case "select_option":
                value = tool_input.get("value", "")
                return f"Выбор опции: {value}"
            case "scroll":
                direction = tool_input.get("direction", "down")
                return f"Прокрутка {direction}"
            case _:
                return f"{tool_name}"
    
    async def _execute_tool_impl(
        self, 
        tool_name: str, 
        tool_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Внутренняя реализация выполнения инструментов.
        
        Args:
            tool_name: Имя инструмента
            tool_input: Параметры
            
        Returns:
            Dict: Результат выполнения
        """
        controller = self.browser_controller
        
        match tool_name:
            case "navigate":
                url = tool_input.get("url", "")
                new_url = await controller.navigate(url)
                return {
                    "success": True,
                    "message": f"Перешли на страницу: {new_url}"
                }
            
            case "click":
                selector = await self._get_selector(tool_input)
                if not selector:
                    return {
                        "success": False,
                        "message": "Не указан селектор или индекс элемента"
                    }
                await controller.click(selector)
                return {
                    "success": True,
                    "message": f"Клик выполнен: {selector}"
                }
            
            case "click_at_coordinates":
                # Получаем координаты напрямую или из элемента
                x = tool_input.get("x")
                y = tool_input.get("y")
                element_index = tool_input.get("element_index")
                
                # Если указан element_index - берём координаты из элемента
                if element_index is not None and (x is None or y is None):
                    page_state = self.context_manager.get_last_page_state()
                    if page_state:
                        elements = page_state.get("interactive_elements", [])
                        if 0 <= element_index < len(elements):
                            position = elements[element_index].get("position", {})
                            x = position.get("x")
                            y = position.get("y")
                
                if x is None or y is None:
                    return {
                        "success": False,
                        "message": "Не указаны координаты (x, y) или element_index"
                    }
                
                await controller.click_at_position(int(x), int(y))
                return {
                    "success": True,
                    "message": f"Клик по координатам ({x}, {y}) выполнен"
                }
            
            case "type_text":
                selector = await self._get_selector(tool_input)
                text = tool_input.get("text", "")
                clear = tool_input.get("clear", True)
                
                if not selector:
                    return {
                        "success": False,
                        "message": "Не указан селектор или индекс элемента"
                    }
                
                await controller.type_text(selector, text, clear_first=clear)
                return {
                    "success": True,
                    "message": f"Текст введён в {selector}"
                }
            
            case "select_option":
                selector = await self._get_selector(tool_input)
                value = tool_input.get("value", "")
                
                if not selector:
                    return {
                        "success": False,
                        "message": "Не указан селектор элемента"
                    }
                
                await controller.select_option(selector, value)
                return {
                    "success": True,
                    "message": f"Выбрана опция '{value}' в {selector}"
                }
            
            case "scroll":
                direction = tool_input.get("direction", "down")
                amount_key = tool_input.get("amount", "medium")
                amount = SCROLL_AMOUNTS.get(amount_key, 500)
                
                if amount == -1:  # page
                    viewport = await controller.page.evaluate("window.innerHeight")
                    amount = viewport
                
                await controller.scroll(direction, amount)
                return {
                    "success": True,
                    "message": f"Прокрутка {direction} на {amount}px"
                }
            
            case "wait":
                selector = tool_input.get("selector")
                timeout = tool_input.get("timeout", Timeouts.WAIT_DEFAULT)
                
                if selector:
                    found = await controller.wait_for(selector, timeout=timeout)
                    if found:
                        return {
                            "success": True,
                            "message": f"Элемент найден: {selector}"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"Элемент не найден за {timeout}ms: {selector}"
                        }
                else:
                    # For non-selector waits, cap at max wait (optimized)
                    actual_timeout = min(timeout, Timeouts.WAIT_MAX)
                    await asyncio.sleep(actual_timeout / 1000)
                    return {
                        "success": True,
                        "message": f"Подождали {actual_timeout}ms"
                    }
            
            case "extract_data":
                query = tool_input.get("query", "")
                page_state = await self.get_page_context()
                
                # Извлекаем текстовое содержимое
                content = page_state.get("text_content", "")
                
                # AUTOMATIC DATA CAPTURE: Store extracted data to prevent loss
                # This data will be automatically used by complete_task if needed
                self._extracted_data = content
                
                # Preview first 500 chars for reference
                preview = content[:500] if len(content) > 500 else content
                
                # Simplified message - data is automatically captured
                return {
                    "success": True,
                    "message": f"""Данные извлечены и автоматически сохранены ({len(content)} символов).
Предварительный просмотр: {preview}{'...' if len(content) > 500 else ''}

Теперь вызови complete_task с кратким описанием результата в summary.
Данные будут автоматически включены в результат."""
                }
            
            case "go_back":
                url = await controller.go_back()
                if url:
                    return {
                        "success": True,
                        "message": f"Вернулись на: {url}"
                    }
                return {
                    "success": False,
                    "message": "Не удалось вернуться назад"
                }
            
            case "refresh":
                url = await controller.refresh()
                return {
                    "success": True,
                    "message": f"Страница обновлена: {url}"
                }
            
            case "take_screenshot":
                full_page = tool_input.get("full_page", False)
                screenshot = await controller.take_screenshot(full_page=full_page)
                
                # В реальности можно сохранить файл или отправить в LLM с vision
                return {
                    "success": True,
                    "message": f"Скриншот создан ({len(screenshot)} bytes)"
                }
            
            case "complete_task":
                # Обрабатывается отдельно в run()
                success = tool_input.get("success", True)
                summary = tool_input.get("summary", "Задача завершена")
                return {
                    "success": success,
                    "message": summary
                }
            
            case "ask_user":
                question = tool_input.get("question", "")
                options = tool_input.get("options", [])
                
                # НЕ вызываем wait_for_input здесь - это делается в run() после получения ответа
                # wait_for_input менял статус на WAITING_INPUT, что выходило из цикла
                
                options_str = f"\nВарианты: {', '.join(options)}" if options else ""
                return {
                    "success": True,
                    "message": f"Вопрос для пользователя: {question}{options_str}\n\nОжидаю ответ..."
                }
            
            case "new_tab":
                url = tool_input.get("url", "about:blank")
                result_url = await controller.new_tab(url)
                return {
                    "success": True,
                    "message": f"Открыта новая вкладка: {result_url}"
                }
            
            case _:
                return {
                    "success": False,
                    "message": f"Неизвестный инструмент: {tool_name}"
                }
    
    async def _get_selector(self, tool_input: Dict[str, Any]) -> Optional[str]:
        """
        Получает селектор из параметров инструмента.
        
        Поддерживает:
        - element_index: индекс из списка интерактивных элементов (приоритет 1)
        - selector: прямой CSS селектор (приоритет 2, только если element_index не указан)
        
        ВАЖНО: element_index предпочтительнее, т.к. использует реальные элементы со страницы.
        AI-provided selector валидируется на существование перед использованием.
        
        Args:
            tool_input: Параметры инструмента
            
        Returns:
            str | None: Селектор или None
        """
        # Приоритет 1: индекс элемента (ссылается на реальные элементы страницы)
        element_index = tool_input.get("element_index")
        if element_index is not None:
            # Получаем элемент из последнего состояния страницы
            page_state = self.context_manager.get_last_page_state()
            if page_state:
                elements = page_state.get("interactive_elements", [])
                if 0 <= element_index < len(elements):
                    return elements[element_index].get("selector")
            # element_index указан, но невалиден - возвращаем None
            logger.warning(f"Invalid element_index: {element_index}")
            return None
        
        # Приоритет 2: прямой селектор (только если element_index NOT provided)
        selector = tool_input.get("selector")
        if selector:
            # Валидируем что селектор существует на странице
            page = self.browser_controller.page
            if page:
                try:
                    element = await page.query_selector(selector)
                    if element is None:
                        logger.warning(f"AI provided selector not found on page: {selector}")
                        return None
                    return selector
                except Exception as e:
                    logger.warning(f"Invalid selector syntax: {selector} - {e}")
                    return None
            else:
                # Нет страницы - возвращаем селектор как есть (будет ошибка при клике)
                return selector
        
        return None
    
    def _format_action_for_reflection(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """
        Форматирует действие для списка рефлексии.
        
        Args:
            tool_name: Имя инструмента
            tool_input: Параметры
            
        Returns:
            str: Человекочитаемое описание действия
        """
        match tool_name:
            case "navigate":
                url = tool_input.get("url", "")[:50]
                return f"navigate → {url}"
            case "click":
                selector = tool_input.get("selector", "")[:30]
                element_idx = tool_input.get("element_index", "")
                target = selector or f"element[{element_idx}]"
                return f"click → {target}"
            case "click_at_coordinates":
                x = tool_input.get("x", 0)
                y = tool_input.get("y", 0)
                return f"click_at_coordinates({x}, {y})"
            case "type_text":
                text = tool_input.get("text", "")[:20]
                return f"type_text → \"{text}...\""
            case "scroll":
                direction = tool_input.get("direction", "down")
                return f"scroll → {direction}"
            case "extract_data":
                return "extract_data"
            case "complete_task":
                return "complete_task"
            case _:
                return tool_name
    
    def _get_action_key(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """
        Создает ключ действия для детекции зацикливания.
        
        Args:
            tool_name: Имя инструмента
            tool_input: Параметры
            
        Returns:
            str: Уникальный ключ действия
        """
        # Для navigate - используем URL
        if tool_name == "navigate":
            return f"navigate:{tool_input.get('url', '')}"
        
        # Для click/type_text - используем селектор или индекс
        if tool_name in ("click", "type_text"):
            selector = tool_input.get("selector", "")
            element_idx = tool_input.get("element_index", "")
            target = selector or f"idx:{element_idx}"
            return f"{tool_name}:{target}"
        
        # Для extract_data - используем query
        if tool_name == "extract_data":
            return f"extract_data:{tool_input.get('query', '')[:30]}"
        
        # Для scroll - направление
        if tool_name == "scroll":
            return f"scroll:{tool_input.get('direction', 'down')}"
        
        # Для остальных - просто имя
        return tool_name
    
    def _check_loop_detection(
        self,
        recent_actions: list[str],
        max_repeated: int
    ) -> tuple[bool, str]:
        """
        Проверяет на зацикливание (повторение одного действия).
        
        Args:
            recent_actions: Список последних действий
            max_repeated: Максимум повторений
            
        Returns:
            tuple[bool, str]: (обнаружено_зацикливание, сообщение)
        """
        if len(recent_actions) < max_repeated:
            return False, ""
        
        # Проверяем последние N действий
        last_n = recent_actions[-max_repeated:]
        
        # Если все одинаковые - зацикливание
        if len(set(last_n)) == 1:
            return True, f"Действие '{last_n[0]}' повторено {max_repeated} раз подряд"
        
        # Проверяем паттерн A-B-A-B (чередование двух действий)
        if len(recent_actions) >= 4:
            last_4 = recent_actions[-4:]
            if last_4[0] == last_4[2] and last_4[1] == last_4[3] and last_4[0] != last_4[1]:
                return True, f"Чередование действий: {last_4[0]} ↔ {last_4[1]}"
        
        return False, ""
    
    def _safe_trim_messages(
        self,
        messages: List[Dict[str, Any]],
        max_history: int
    ) -> List[Dict[str, Any]]:
        """
        Безопасная обрезка истории сообщений с удалением orphan tool_result.
        
        Anthropic API требует, чтобы каждый tool_result имел соответствующий
        tool_use в истории. При обрезке может нарушиться эта связь,
        что приводит к ошибке 400.
        
        АГРЕССИВНЫЙ ПОДХОД: Полностью удаляем orphan tool_result блоки,
        не пытаясь восстанавливать tool_use из отброшенных сообщений.
        
        Args:
            messages: Список сообщений
            max_history: Целевой размер истории
            
        Returns:
            List[Dict]: Безопасно обрезанный список сообщений без orphan tool_result
        """
        if len(messages) <= max_history:
            return self._remove_orphan_tool_results(messages)
        
        # Шаг 1: Обрезаем до max_history
        trimmed = messages[-max_history:]
        
        # Шаг 2: Удаляем все orphan tool_result
        cleaned = self._remove_orphan_tool_results(trimmed)
        
        logger.debug(
            f"Safe trim: {len(messages)} -> {len(cleaned)} messages"
        )
        
        return cleaned
    
    def _remove_orphan_tool_results(
        self,
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Удаляет все tool_result блоки, у которых нет соответствующего tool_use.
        
        Поддерживает оба формата:
        - Anthropic: role="user" с content=[{type: "tool_result", tool_use_id: ...}]
        - OpenAI/OpenRouter: role="tool" с tool_call_id: ...
        
        Args:
            messages: Список сообщений
            
        Returns:
            List[Dict]: Очищенный список без orphan tool_result
        """
        # Шаг 1: Собираем все tool_use IDs из assistant сообщений
        tool_use_ids = set()
        
        for msg in messages:
            if msg.get("role") == "assistant":
                # Anthropic format: content list with tool_use blocks
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_id = block.get("id")
                            if tool_id:
                                tool_use_ids.add(tool_id)
                
                # OpenRouter/OpenAI format: tool_calls array
                tool_calls = msg.get("tool_calls", [])
                if isinstance(tool_calls, list):
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            tc_id = tc.get("id")
                            if tc_id:
                                tool_use_ids.add(tc_id)
        
        # Шаг 2: Фильтруем сообщения, удаляя orphan tool_result
        cleaned_messages = []
        removed_count = 0
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", [])
            
            # OpenAI/OpenRouter format: role="tool" messages
            # Эти сообщения являются tool_result в OpenAI формате
            if role == "tool":
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id in tool_use_ids:
                    # tool_use существует - оставляем
                    cleaned_messages.append(msg)
                else:
                    # orphan tool result (OpenAI format) - удаляем
                    removed_count += 1
                    logger.debug(f"Removing orphan tool result (OpenAI format): {tool_call_id}")
                continue
            
            # Anthropic format: role="user" с tool_result блоками в content
            if role == "user" and isinstance(content, list):
                cleaned_content = []
                
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id in tool_use_ids:
                            # tool_use существует - оставляем
                            cleaned_content.append(block)
                        else:
                            # orphan tool_result - удаляем
                            removed_count += 1
                            logger.debug(f"Removing orphan tool_result (Anthropic format): {tool_use_id}")
                    else:
                        # Не tool_result - оставляем
                        cleaned_content.append(block)
                
                # Если после очистки контент не пустой - добавляем сообщение
                if cleaned_content:
                    cleaned_msg = {**msg, "content": cleaned_content}
                    cleaned_messages.append(cleaned_msg)
                elif not content:
                    # Если исходный контент был пустой - добавляем как есть
                    cleaned_messages.append(msg)
                # Если контент стал пустой после очистки - пропускаем сообщение
                
            elif role == "user" and isinstance(content, str):
                # Строковый контент - оставляем как есть
                cleaned_messages.append(msg)
            else:
                # assistant или другие роли - оставляем как есть
                cleaned_messages.append(msg)
        
        if removed_count > 0:
            logger.info(f"Removed {removed_count} orphan tool_result blocks")
        
        return cleaned_messages
    
    def _build_combined_tool_result_message(
        self,
        tool_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Объединяет все tool_result в одно сообщение.
        
        Anthropic API требует, чтобы все tool_result для одного assistant message
        с tool_use были в ОДНОМ user message. Эта функция объединяет результаты.
        
        Args:
            tool_results: Список результатов с ключами:
                - tool_call_id: ID tool call
                - result: Текст результата
                - is_error: Флаг ошибки
                
        Returns:
            Dict: Объединённое сообщение в формате для messages API
        """
        # Для OpenRouter и Custom используем OpenAI-compatible format
        # В OpenAI каждый tool result - отдельное сообщение с role="tool"
        if self.llm_client.provider in ("openrouter", "custom"):
            # OpenAI format: возвращаем первый результат, остальные добавятся отдельно
            # Но на самом деле OpenAI поддерживает multiple tool messages подряд
            # Однако мы используем другой подход - собираем в список
            # Для совместимости с текущей архитектурой, возвращаем список
            # который будет развернут в messages
            if len(tool_results) == 1:
                tr = tool_results[0]
                return {
                    "role": "tool",
                    "tool_call_id": tr["tool_call_id"],
                    "content": tr["result"]
                }
            else:
                # Для множественных результатов создаём специальную структуру
                # которую нужно обработать в вызывающем коде
                # Возвращаем первый, остальные должны быть добавлены отдельно
                # TODO: Рефакторинг для полной поддержки multiple tool results в OpenAI
                return {
                    "_multiple_tool_results": True,
                    "results": [
                        {
                            "role": "tool",
                            "tool_call_id": tr["tool_call_id"],
                            "content": tr["result"]
                        }
                        for tr in tool_results
                    ]
                }
        
        # Для Anthropic - все tool_result в одном user message
        content = []
        for tr in tool_results:
            content.append({
                "type": "tool_result",
                "tool_use_id": tr["tool_call_id"],
                "content": tr["result"],
                "is_error": tr.get("is_error", False)
            })
        
        return {
            "role": "user",
            "content": content
        }
    
    async def _handle_ask_user(self, question: str) -> Optional[str]:
        """
        Обрабатывает ask_user - ждет ответа пользователя.
        
        Args:
            question: Вопрос к пользователю
            
        Returns:
            str | None: Ответ пользователя или None
        """
        logger.info(f"❓ Вопрос пользователю: {question}")
        await self._notify_status(f"Ожидание ответа: {question[:50]}...")
        
        # Если есть callback - используем его
        if hasattr(self, '_user_response_callback') and self._user_response_callback:
            try:
                answer = await self._user_response_callback(question)
                logger.info(f"✅ Получен ответ: {answer[:50]}..." if answer else "Пустой ответ")
                return answer
            except Exception as e:
                logger.error(f"Ошибка получения ответа: {e}")
                return f"Ошибка: не удалось получить ответ пользователя"
        
        # Если callback нет - используем input() в отдельном потоке (для CLI)
        try:
            import sys
            if sys.stdin.isatty():
                # Консольный режим - читаем из stdin
                print(f"\n{'='*50}")
                print(f"❓ ВОПРОС ОТ АГЕНТА: {question}")
                print(f"{'='*50}")
                
                # Используем asyncio для неблокирующего ввода
                loop = asyncio.get_event_loop()
                answer = await loop.run_in_executor(None, input, "Ваш ответ: ")
                
                logger.info(f"✅ Получен ответ из консоли: {answer[:50]}..." if answer else "Пустой ответ")
                return answer
            else:
                # Не интерактивный режим
                logger.warning("Не интерактивный режим - возвращаем заглушку")
                return "Пользователь не может ответить (неинтерактивный режим)"
        except Exception as e:
            logger.error(f"Ошибка чтения ввода: {e}")
            return None
    
    def _handle_task_completion(self, tool_input: Dict[str, Any]) -> TaskResult:
        """
        Обрабатывает завершение задачи.
        
        Args:
            tool_input: Параметры complete_task
            
        Returns:
            TaskResult: Результат задачи
        """
        success = tool_input.get("success", True)
        summary = tool_input.get("summary", "Задача завершена")
        result_data = tool_input.get("result")
        
        # AUTOMATIC DATA CAPTURE: Check if we need to use stored extracted data
        # This prevents data loss when LLM forgets to include data in complete_task
        original_task = self.task_manager.current_task.description.lower() if self.task_manager.current_task else ""
        extraction_keywords = ["извлеч", "прочита", "расскаж", "покаж", "найди", "список", "письм"]
        is_extraction_task = any(keyword in original_task for keyword in extraction_keywords)
        
        # If this is an extraction task, check if result is missing or too generic
        if is_extraction_task:
            generic_phrases = ["проанализиро", "извлечены данные", "извлечено", "данные получены", "информация получена"]
            result_is_empty = not result_data or len(result_data.strip()) == 0
            result_is_too_short = result_data and len(result_data) < 50
            result_is_generic = result_data and any(phrase in result_data.lower() for phrase in generic_phrases)
            
            # Automatically use stored extracted data if result is problematic
            if (result_is_empty or result_is_too_short or result_is_generic) and self._extracted_data:
                logger.info(
                    f"✓ Automatic data capture activated: Using stored extracted data "
                    f"({len(self._extracted_data)} chars) instead of incomplete result"
                )
                result_data = self._extracted_data
            elif result_data and len(result_data) < 100:
                logger.warning(
                    f"⚠️ Result seems too short for data extraction task. "
                    f"Length: {len(result_data)} chars. Task: '{original_task[:50]}...'"
                )
                logger.warning(f"Result preview: {result_data[:100]}...")
        
        # Clear extracted data after use to prevent leakage to next task
        self._extracted_data = None
        
        if success:
            return self.task_manager.complete(summary, data=result_data)
        else:
            return self.task_manager.fail(summary)
    
    def _log_tool_call(self, tool_name: str, tool_input: Dict[str, Any], result: Dict[str, Any]) -> None:
        """
        Логирует вызов инструмента в зависимости от текущего режима.
        
        Args:
            tool_name: Имя инструмента
            tool_input: Параметры инструмента
            result: Результат выполнения
        """
        config = get_config()
        
        if config.log_mode == "verbose":
            self._log_verbose(tool_name, tool_input, result)
        else:
            self._log_compact(tool_name, tool_input, result)
    
    def _log_verbose(self, tool_name: str, tool_input: Dict[str, Any], result: Dict[str, Any]) -> None:
        """
        Verbose mode - показывает полную информацию о tool call.
        
        Формат:
            Using tool: click_element
              Input: {
                "selector": "#15"
              }
            Result: Clicked element: #15
        
        Args:
            tool_name: Имя инструмента
            tool_input: Параметры инструмента
            result: Результат выполнения
        """
        print(f"Using tool: {tool_name}")
        print(f"  Input: {{")
        for key, value in tool_input.items():
            print(f'    "{key}": {json.dumps(value, ensure_ascii=False)}')
        print(f"  }}")
        print(f"Result: {result.get('message', '')}")
        print()
    
    def _log_compact(self, tool_name: str, tool_input: Dict[str, Any], result: Dict[str, Any]) -> None:
        """
        Compact mode - простое отображение действий.
        
        Формат:
            ● Клик на элемент #15
            ● Ввод текста: "бургер"
        
        Args:
            tool_name: Имя инструмента
            tool_input: Параметры инструмента
            result: Результат выполнения
        """
        action_map = {
            "navigate": f"● Переход на {tool_input.get('url', '')}",
            "click": f"● Клик на элемент {tool_input.get('element_index', tool_input.get('selector', ''))}",
            "click_at_coordinates": f"● Клик по координатам ({tool_input.get('x', 0)}, {tool_input.get('y', 0)})",
            "type_text": f"● Ввод текста: \"{tool_input.get('text', '')}\"",
            "select_option": f"● Выбор опции: {tool_input.get('value', '')}",
            "scroll": f"● Прокрутка {tool_input.get('direction', 'down')}",
            "wait": f"● Пауза {tool_input.get('timeout', 0)}ms",
            "extract_data": f"● Извлечение данных",
            "go_back": "● Назад",
            "refresh": "● Обновление страницы",
            "take_screenshot": "● Скриншот",
            "complete_task": f"● Завершение: {tool_input.get('summary', '')[:50]}",
            "ask_user": f"● Вопрос пользователю: {tool_input.get('question', '')[:50]}",
        }
        
        message = action_map.get(tool_name, f"● {tool_name}")
        print(message)
    
    async def _notify_action(self, action: str, params: Dict) -> None:
        """Уведомляет о выполняемом действии."""
        if self._on_action:
            try:
                await self._on_action(action, params)
            except Exception as e:
                logger.warning(f"Ошибка callback on_action: {e}")
    
    async def _notify_status(self, status: str) -> None:
        """Уведомляет об изменении статуса."""
        if self._on_status:
            try:
                await self._on_status(status)
            except Exception as e:
                logger.warning(f"Ошибка callback on_status: {e}")
    
    async def __aenter__(self) -> "BrowserAgent":
        """Поддержка async context manager."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Закрытие при выходе из контекста."""
        await self.stop()