"""
LLM Client - клиент для взаимодействия с Claude API.

Обрабатывает отправку сообщений, получение ответов и
извлечение tool_use блоков из ответа.
"""

import logging
from typing import Optional, List, Dict, Any, Literal
from dataclasses import dataclass, field

import anthropic
from anthropic import AsyncAnthropic, APIError, APIConnectionError, RateLimitError

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from .tools import BROWSER_TOOLS
from .prompts import SYSTEM_PROMPT


logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """
    Представляет вызов инструмента от LLM.
    
    Attributes:
        id: Уникальный идентификатор вызова (для tool_result)
        name: Имя инструмента
        input: Параметры вызова
    """
    id: str
    name: str
    input: Dict[str, Any] = field(default_factory=dict)


@dataclass  
class LLMResponse:
    """
    Ответ от LLM.
    
    Attributes:
        content: Текстовый ответ (если есть)
        tool_calls: Список вызовов инструментов
        stop_reason: Причина остановки (end_turn, tool_use, max_tokens)
        usage: Информация об использовании токенов
    """
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    stop_reason: str = ""
    usage: Dict[str, int] = field(default_factory=dict)


class LLMClientError(Exception):
    """Базовое исключение для ошибок LLM клиента."""
    pass


class LLMConnectionError(LLMClientError):
    """Ошибка подключения к API."""
    pass


class LLMRateLimitError(LLMClientError):
    """Превышен лимит запросов."""
    pass


class LLMClient:
    """
    Клиент для взаимодействия с Claude API.
    
    Поддерживает:
    - Отправку сообщений с системным промптом
    - Function/Tool calling
    - Обработку tool_use блоков в ответе
    - Формирование tool_result для продолжения диалога
    
    Attributes:
        model: Название модели Claude
        max_tokens: Максимальное количество токенов в ответе
        
    Example:
        ```python
        client = LLMClient(api_key="sk-ant-...")
        
        response = await client.send_message(
            messages=[{"role": "user", "content": "Перейди на google.com"}],
            tools=BROWSER_TOOLS,
            system_prompt=SYSTEM_PROMPT
        )
        
        if response.tool_calls:
            for tool_call in response.tool_calls:
                print(f"Вызов: {tool_call.name}({tool_call.input})")
        ```
    """
    
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        provider: Literal["anthropic", "openrouter", "custom"] = "anthropic",
        base_url: Optional[str] = None
    ):
        """
        Инициализирует LLM клиент.
        
        Args:
            api_key: API ключ (Anthropic, OpenRouter или Custom)
            model: Модель для использования
            max_tokens: Максимальное количество токенов в ответе
            provider: Провайдер API ("anthropic", "openrouter" или "custom")
            base_url: Кастомный base URL для API (только для provider="custom")
        """
        self.model = model
        self.max_tokens = max_tokens
        self.provider = provider
        self.base_url = base_url
        
        if provider == "openrouter":
            if not OPENAI_AVAILABLE:
                raise ImportError("OpenAI library required for OpenRouter. Install with: pip install openai")
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1"
            )
            logger.info(f"LLMClient инициализирован: provider=OpenRouter, model={model}")
        elif provider == "custom":
            if not base_url:
                raise ValueError("base_url is required for custom provider")
            if not OPENAI_AVAILABLE:
                raise ImportError("OpenAI library required for custom endpoint. Install with: pip install openai")
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url
            )
            logger.info(f"LLMClient инициализирован: provider=Custom, base_url={base_url}, model={model}")
        else:
            self._client = AsyncAnthropic(api_key=api_key)
            logger.info(f"LLMClient инициализирован: provider=Anthropic, model={model}")
    
    async def send_message(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """
        Отправляет сообщение в Claude API и получает ответ.
        
        Args:
            messages: Список сообщений в формате Chat Messages API
                [{"role": "user", "content": "..."}, ...]
            tools: Определения инструментов (по умолчанию BROWSER_TOOLS)
            system_prompt: Системный промпт (по умолчанию SYSTEM_PROMPT)
            
        Returns:
            LLMResponse: Ответ от модели с текстом и/или tool_calls
            
        Raises:
            LLMConnectionError: Ошибка подключения к API
            LLMRateLimitError: Превышен лимит запросов
            LLMClientError: Другие ошибки API
        """
        if tools is None:
            tools = BROWSER_TOOLS
        
        if system_prompt is None:
            system_prompt = SYSTEM_PROMPT
        
        try:
            logger.debug(f"Отправка сообщения: {len(messages)} сообщений")
            
            if self.provider == "openrouter" or self.provider == "custom":
                return await self._send_openrouter(messages, tools, system_prompt)
            else:
                return await self._send_anthropic(messages, tools, system_prompt)
            
        except APIConnectionError as e:
            logger.error(f"Ошибка подключения к API: {e}")
            raise LLMConnectionError(f"Не удалось подключиться к API: {e}") from e
            
        except RateLimitError as e:
            logger.error(f"Превышен лимит запросов: {e}")
            raise LLMRateLimitError(f"Превышен лимит запросов: {e}") from e
            
        except (APIError, Exception) as e:
            logger.error(f"Ошибка API: {e}")
            raise LLMClientError(f"Ошибка API: {e}") from e
    
    async def _send_anthropic(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str
    ) -> LLMResponse:
        """Отправка через Anthropic API."""
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            tools=tools,
            messages=messages
        )
        return self._parse_response(response)
    
    async def _send_openrouter(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str
    ) -> LLMResponse:
        """Отправка через OpenRouter API (совместимый с OpenAI)."""
        # Преобразуем сообщения в формат OpenAI
        openai_messages = [{"role": "system", "content": system_prompt}]
        
        for msg in messages:
            openai_messages.append(msg)
        
        response = await self._client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=openai_messages,
            tools=self._convert_tools_to_openai(tools) if tools else None
        )
        
        return self._parse_openrouter_response(response)
    
    def _convert_tools_to_openai(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Конвертирует Anthropic tool format в OpenAI format."""
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {})
                }
            })
        return openai_tools
    
    def _parse_openrouter_response(self, response) -> LLMResponse:
        """Парсит ответ от OpenRouter API."""
        choice = response.choices[0]
        message = choice.message
        
        result = LLMResponse(
            stop_reason=choice.finish_reason,
            usage={
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens
            }
        )
        
        # Текстовый контент
        if message.content:
            result.content = message.content
        
        # Tool calls
        if message.tool_calls:
            import json
            for tc in message.tool_calls:
                # Safely parse arguments - handle None or empty string
                arguments = tc.function.arguments
                if arguments is None or arguments == "":
                    tool_input = {}
                else:
                    try:
                        tool_input = json.loads(arguments)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.error(f"Failed to parse tool arguments: {arguments}, error: {e}")
                        tool_input = {}
                
                tool_call = ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    input=tool_input
                )
                result.tool_calls.append(tool_call)
                logger.debug(f"Tool call: {tool_call.name}({tool_call.input})")
        
        logger.debug(
            f"Ответ получен: {len(result.content)} символов, "
            f"{len(result.tool_calls)} tool calls, "
            f"stop_reason={result.stop_reason}"
        )
        
        return result
    
    def _parse_response(self, response: anthropic.types.Message) -> LLMResponse:
        """
        Парсит ответ от Claude API.
        
        Args:
            response: Сырой ответ от API
            
        Returns:
            LLMResponse: Распарсенный ответ
        """
        result = LLMResponse(
            stop_reason=response.stop_reason,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }
        )
        
        # Обрабатываем content blocks
        for block in response.content:
            if block.type == "text":
                result.content += block.text
            elif block.type == "tool_use":
                tool_call = ToolCall(
                    id=block.id,
                    name=block.name,
                    input=block.input
                )
                result.tool_calls.append(tool_call)
                logger.debug(f"Tool call: {tool_call.name}({tool_call.input})")
        
        logger.debug(
            f"Ответ получен: {len(result.content)} символов, "
            f"{len(result.tool_calls)} tool calls, "
            f"stop_reason={result.stop_reason}"
        )
        
        return result
    
    async def process_tool_calls(
        self, 
        response: LLMResponse
    ) -> List[ToolCall]:
        """
        Извлекает все tool calls из ответа.
        
        Args:
            response: Ответ от LLM
            
        Returns:
            List[ToolCall]: Список вызовов инструментов
        """
        return response.tool_calls
    
    def build_tool_result_message(
        self,
        tool_call_id: str,
        result: str,
        is_error: bool = False
    ) -> Dict[str, Any]:
        """
        Формирует сообщение с результатом выполнения tool call.
        
        Используется для отправки результата обратно в Claude
        после выполнения инструмента.
        
        Args:
            tool_call_id: ID tool call из ToolCall.id
            result: Результат выполнения (строка)
            is_error: Это сообщение об ошибке?
            
        Returns:
            Dict: Сообщение в формате для messages API
            
        Example:
            ```python
            tool_result = client.build_tool_result_message(
                tool_call_id="toolu_xxx",
                result="Успешно перешли на https://google.com",
                is_error=False
            )
            messages.append(tool_result)
            ```
        """
        # Для OpenRouter и Custom используем OpenAI-compatible format
        if self.provider == "openrouter" or self.provider == "custom":
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result
            }
        
        # Для Anthropic используем их формат
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": result,
                    "is_error": is_error
                }
            ]
        }
    
    def build_assistant_tool_use_message(
        self,
        tool_calls: List[ToolCall],
        text_content: str = ""
    ) -> Dict[str, Any]:
        """
        Формирует сообщение assistant с tool_use блоками.
        
        Нужно для сохранения в истории сообщений после того,
        как модель вернула tool_use.
        
        Args:
            tool_calls: Список tool calls из ответа
            text_content: Текстовый контент (если был)
            
        Returns:
            Dict: Сообщение assistant для истории
        """
        # Для OpenRouter и Custom используем OpenAI-compatible format
        if self.provider == "openrouter" or self.provider == "custom":
            import json
            message = {
                "role": "assistant",
                "content": text_content if text_content else None
            }
            
            # Tool calls в отдельном поле для OpenAI format
            if tool_calls:
                message["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.input)
                        }
                    }
                    for tc in tool_calls
                ]
            
            return message
        
        # Для Anthropic используем их формат
        content = []
        
        if text_content:
            content.append({
                "type": "text",
                "text": text_content
            })
        
        for tc in tool_calls:
            content.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.name,
                "input": tc.input
            })
        
        return {
            "role": "assistant",
            "content": content
        }
    
    async def get_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Простой метод для получения текстового ответа без tool calling.
        
        Args:
            prompt: Текст запроса
            system_prompt: Системный промпт (опционально)
            
        Returns:
            str: Текстовый ответ модели
        """
        messages = [{"role": "user", "content": prompt}]
        
        response = await self.send_message(
            messages=messages,
            tools=[],  # Без инструментов
            system_prompt=system_prompt or "Ты полезный AI ассистент."
        )
        
        return response.content
    
    async def close(self):
        """
        Закрывает клиент и освобождает ресурсы.
        
        Вызывайте при завершении работы с клиентом.
        """
        await self._client.close()
        logger.info("LLMClient закрыт")
    
    async def __aenter__(self) -> "LLMClient":
        """Поддержка async context manager."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Закрытие при выходе из контекста."""
        await self.close()