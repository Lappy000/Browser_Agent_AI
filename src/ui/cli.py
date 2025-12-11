"""
CLI - командный интерфейс для Browser Agent.

Использует rich для красивого вывода с цветами,
прогрессом и панелями.
"""

import asyncio
import logging
import time
import sys
from typing import Optional, Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich import box

from ..core.agent import BrowserAgent, AgentError
from ..core.task_manager import TaskResult, TaskStatus
from ..security.security_layer import SecurityLayer

logger = logging.getLogger(__name__)


# Версия приложения
VERSION = "1.0.0"


class CLI:
    """
    Командный интерфейс для Browser Agent.
    
    Предоставляет:
    - Красивый ASCII баннер
    - Ввод задач от пользователя  
    - Отображение прогресса выполнения
    - Запросы подтверждения для опасных действий
    - Итоговые отчёты
    
    Example:
        ```python
        cli = CLI()
        await cli.run()
        ```
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Инициализирует CLI.
        
        Args:
            api_key: API ключ Anthropic (опционально, берётся из .env)
        """
        # На Windows принудительно устанавливаем UTF-8 для консоли
        if sys.platform == "win32":
            try:
                sys.stdout.reconfigure(encoding='utf-8')
                sys.stderr.reconfigure(encoding='utf-8')
            except (AttributeError, TypeError):
                # Если reconfigure не доступен, пытаемся через chcp
                import os
                os.system('chcp 65001 >nul 2>&1')
        
        self.console = Console()
        self._api_key = api_key
        self._agent: Optional[BrowserAgent] = None
        self._security: Optional[SecurityLayer] = None
        self._current_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._current_action = ""
        self._current_url = ""
        
    def _print_banner(self) -> None:
        """Выводит красивый ASCII баннер при запуске."""
        banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║          🌐  [bold cyan]Browser Agent[/bold cyan] v{version}                       ║
║                                                              ║
║      [dim]AI-агент для автоматизации браузера[/dim]                 ║
║      [dim]Powered by Claude AI & Playwright[/dim]                   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""".format(version=VERSION)
        
        self.console.print(banner)
        self.console.print(
            "[dim]Введите задачу для выполнения или 'help' для справки[/dim]\n"
        )
    
    def _print_help(self) -> None:
        """Выводит справку по командам."""
        help_table = Table(
            title="📖 Справка по командам",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )
        
        help_table.add_column("Команда", style="cyan", width=20)
        help_table.add_column("Описание", style="white")
        
        help_table.add_row("help", "Показать эту справку")
        help_table.add_row("exit / quit / выход", "Выйти из программы")
        help_table.add_row("status", "Показать текущий статус")
        help_table.add_row("stop", "Остановить текущую задачу")
        help_table.add_row("[текст задачи]", "Выполнить задачу")
        
        self.console.print()
        self.console.print(help_table)
        self.console.print()
        
        # Примеры задач
        examples = Panel(
            "[bold]Примеры задач:[/bold]\n\n"
            "• Перейди на google.com и найди погоду в Москве\n"
            "• Открой hh.ru и найди вакансии Python разработчика\n"
            "• Зайди на wikipedia.org и найди информацию о Python\n"
            "• Перейди на github.com и найди репозиторий playwright",
            title="💡 Примеры",
            border_style="green"
        )
        self.console.print(examples)
    
    def _print_status(self) -> None:
        """Выводит текущий статус агента."""
        status_table = Table(
            title="📊 Статус",
            box=box.ROUNDED
        )
        
        status_table.add_column("Параметр", style="cyan")
        status_table.add_column("Значение", style="white")
        
        agent_status = "🟢 Запущен" if self._agent and self._agent._is_started else "🔴 Не запущен"
        task_status = "🔄 Выполняется" if self._is_running else "⏸️ Ожидание"
        
        status_table.add_row("Агент", agent_status)
        status_table.add_row("Задача", task_status)
        status_table.add_row("Текущий URL", self._current_url or "—")
        status_table.add_row("Действие", self._current_action or "—")
        
        self.console.print()
        self.console.print(status_table)
        self.console.print()
    
    async def confirm_action(self, action: str, risk_reason: str) -> bool:
        """
        Callback для SecurityLayer - показывает красивое окно
        подтверждения для опасных действий.
        
        Args:
            action: Описание действия
            risk_reason: Причина запроса подтверждения
            
        Returns:
            bool: True если пользователь подтвердил
        """
        # Создаём панель предупреждения
        warning_content = Text()
        warning_content.append("\n⚠️  ", style="bold yellow")
        warning_content.append("ТРЕБУЕТСЯ ПОДТВЕРЖДЕНИЕ\n\n", style="bold yellow")
        warning_content.append("Действие: ", style="bold")
        warning_content.append(f"{action}\n\n", style="white")
        warning_content.append("Причина: ", style="bold")
        warning_content.append(f"{risk_reason}\n", style="red")
        
        panel = Panel(
            warning_content,
            title="[bold red]🛡️ Security Check[/bold red]",
            border_style="red",
            box=box.DOUBLE
        )
        
        self.console.print()
        self.console.print(panel)
        
        # Запрашиваем подтверждение
        confirmed = Confirm.ask(
            "[bold yellow]Разрешить это действие?[/bold yellow]",
            default=False
        )
        
        if confirmed:
            self.console.print("[green]✓ Действие разрешено[/green]\n")
        else:
            self.console.print("[red]✗ Действие отклонено[/red]\n")
        
        return confirmed
    
    async def _on_action(self, action: str, params: Dict[str, Any]) -> None:
        """Callback при выполнении действия агентом."""
        self._current_action = action
        
        # Форматируем вывод
        action_text = self._format_action(action, params)
        self.console.print(f"[cyan]●[/cyan] {action_text}")
    
    async def _on_status(self, status: str) -> None:
        """Callback при изменении статуса."""
        self.console.print(f"[dim]→ {status}[/dim]")
    
    def _format_action(self, action: str, params: Dict[str, Any]) -> str:
        """Форматирует действие для вывода."""
        match action:
            case "navigate":
                url = params.get("url", "")
                self._current_url = url
                return f"[bold]Переход на[/bold] {url}"
            
            case "click":
                selector = params.get("selector", "")
                element_idx = params.get("element_index", "")
                target = selector or f"элемент #{element_idx}"
                return f"[bold]Клик[/bold] на {target}"
            
            case "type_text":
                text = params.get("text", "")
                preview = text[:30] + "..." if len(text) > 30 else text
                return f"[bold]Ввод текста:[/bold] \"{preview}\""
            
            case "scroll":
                direction = params.get("direction", "down")
                return f"[bold]Прокрутка[/bold] {direction}"
            
            case "wait":
                timeout = params.get("timeout", 0)
                selector = params.get("selector")
                if selector:
                    return f"[bold]Ожидание[/bold] элемента {selector}"
                return f"[bold]Пауза[/bold] {timeout}ms"
            
            case "extract_data":
                query = params.get("query", "")
                return f"[bold]Извлечение данных:[/bold] {query}"
            
            case "complete_task":
                return "[bold green]Завершение задачи[/bold green]"
            
            case _:
                return f"[bold]{action}[/bold]: {params}"
    
    def _print_result(self, result: TaskResult, elapsed_time: float) -> None:
        """Выводит итоговый результат выполнения задачи."""
        # Получаем статистику токенов
        token_stats = self._agent.get_token_stats() if self._agent else None
        
        # Формируем текст результата
        if result.status == TaskStatus.COMPLETED:
            result_text = (
                f"[bold green]✅ Задача выполнена[/bold green]\n\n"
                f"[bold]Результат:[/bold] {result.summary}\n\n"
                f"[dim]Итераций: {result.actions_count}[/dim]\n"
                f"[dim]Время выполнения: {elapsed_time:.1f} сек[/dim]"
            )
        else:
            result_text = (
                f"[bold red]❌ Задача не выполнена[/bold red]\n\n"
                f"[bold]Причина:[/bold] {result.error or result.summary}\n\n"
                f"[dim]Итераций: {result.actions_count}[/dim]\n"
                f"[dim]Время: {elapsed_time:.1f} сек[/dim]"
            )
        
        # Добавляем статистику токенов если есть
        if token_stats and token_stats["total_tokens"] > 0:
            result_text += (
                f"\n\n[bold cyan]💰 Использование токенов:[/bold cyan]\n"
                f"[dim]Input: {token_stats['input_tokens']:,} | "
                f"Output: {token_stats['output_tokens']:,} | "
                f"Total: {token_stats['total_tokens']:,}[/dim]\n"
                f"[bold yellow]Стоимость: ${token_stats['estimated_cost']:.4f}[/bold yellow]"
            )
        
        result_panel = Panel(
            result_text,
            title=f"[bold {'green' if result.status == TaskStatus.COMPLETED else 'red'}]Результат[/bold {'green' if result.status == TaskStatus.COMPLETED else 'red'}]",
            border_style="green" if result.status == TaskStatus.COMPLETED else "red",
            box=box.ROUNDED
        )
        
        self.console.print()
        self.console.print(result_panel)
        
        # Выводим детальные данные если есть
        if result.data:
            self.console.print()
            data_panel = Panel(
                f"[white]{result.data}[/white]",
                title="[bold cyan]📊 Детальная информация[/bold cyan]",
                border_style="cyan",
                box=box.ROUNDED
            )
            self.console.print(data_panel)
        
        self.console.print()
    
    async def _execute_task(self, task: str) -> None:
        """
        Выполняет задачу с отображением прогресса.
        
        Args:
            task: Текст задачи
        """
        self._is_running = True
        start_time = time.time()
        
        try:
            # Создаём агента если нужно
            if not self._agent:
                self.console.print("[dim]Инициализация агента...[/dim]")
                
                # Создаём security layer с нашим callback
                self._security = SecurityLayer(
                    confirmation_callback=self.confirm_action
                )
                
                self._agent = BrowserAgent(
                    api_key=self._api_key,
                    on_action=self._on_action,
                    on_status=self._on_status,
                    security_layer=self._security
                )
            
            # Запускаем агент если не запущен
            if not self._agent._is_started:
                self.console.print("[cyan]●[/cyan] [bold]Запуск браузера...[/bold]")
                await self._agent.start()
            
            # Выполняем задачу
            self.console.print()
            self.console.print(Panel(
                f"[bold]{task}[/bold]",
                title="🎯 Задача",
                border_style="blue"
            ))
            self.console.print()
            
            result = await self._agent.run(task)
            
            # Выводим результат
            elapsed_time = time.time() - start_time
            self._print_result(result, elapsed_time)
            
        except AgentError as e:
            self.console.print(f"[bold red]Ошибка агента:[/bold red] {e}")
        except Exception as e:
            self.console.print(f"[bold red]Неожиданная ошибка:[/bold red] {e}")
            logger.exception("Ошибка выполнения задачи")
        finally:
            self._is_running = False
            self._current_action = ""
    
    async def _stop_task(self) -> None:
        """Останавливает текущую задачу."""
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            self.console.print("[yellow]⏹️ Задача остановлена[/yellow]")
        else:
            self.console.print("[dim]Нет активной задачи[/dim]")
    
    async def run(self) -> None:
        """
        Главный цикл CLI.
        
        Выводит баннер и обрабатывает команды пользователя.
        """
        self._print_banner()
        
        try:
            while True:
                try:
                    # Получаем ввод от пользователя
                    task = Prompt.ask("\n[bold cyan]Введите задачу[/bold cyan]")
                    task = task.strip()
                    
                    # Проверяем на пустой ввод
                    if not task:
                        continue
                    
                    # Фильтруем UI элементы и бессмысленный ввод
                    # Проверяем наличие специальных символов UI (box-drawing characters)
                    ui_chars = set('═║╔╗╚╝─│┌┐└┘├┤┬┴┼▀▄█▌▐░▒▓■□▪▫')
                    if all(c in ui_chars or c.isspace() for c in task):
                        continue
                    
                    # Проверяем минимальную осмысленную длину
                    # Убираем все UI символы и проверяем что осталось
                    meaningful_task = ''.join(c for c in task if c not in ui_chars)
                    meaningful_task = meaningful_task.strip()
                    
                    if len(meaningful_task) < 3:
                        continue
                    
                    # Обрабатываем команды
                    task_lower = task.lower()
                    
                    if task_lower in ("exit", "quit", "выход", "q"):
                        self.console.print("[dim]До свидания! 👋[/dim]")
                        break
                    
                    if task_lower == "help":
                        self._print_help()
                        continue
                    
                    if task_lower == "status":
                        self._print_status()
                        continue
                    
                    if task_lower == "stop":
                        await self._stop_task()
                        continue
                    
                    # Выполняем задачу
                    self._current_task = asyncio.create_task(
                        self._execute_task(task)
                    )
                    await self._current_task
                    
                except KeyboardInterrupt:
                    self.console.print("\n[yellow]Прервано пользователем[/yellow]")
                    continue
                except asyncio.CancelledError:
                    continue
                    
        finally:
            # Закрываем агента
            if self._agent:
                self.console.print("[dim]Закрытие браузера...[/dim]")
                await self._agent.stop()


async def run_cli(api_key: Optional[str] = None) -> None:
    """
    Запускает CLI интерфейс.
    
    Args:
        api_key: API ключ Anthropic (опционально)
    """
    cli = CLI(api_key=api_key)
    await cli.run()