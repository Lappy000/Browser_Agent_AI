"""
BrowserController - управление браузером через Playwright.

Предоставляет высокоуровневый интерфейс для взаимодействия
с браузером: навигация, клики, ввод текста и т.д.
"""

import logging
import asyncio
import random
from typing import Optional, Literal
from pathlib import Path

from playwright.async_api import (
    async_playwright,
    Playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

from ..config import BrowserConfig, get_config
from ..constants import Timeouts, Retries, HumanLikeDelays
from ..security.url_validator import URLValidator, URLValidationError


logger = logging.getLogger(__name__)


class BrowserError(Exception):
    """Базовое исключение для ошибок браузера."""
    pass


class ElementNotFoundError(BrowserError):
    """Элемент не найден на странице."""
    pass


class NavigationError(BrowserError):
    """Ошибка навигации."""
    pass


class BrowserController:
    """
    Контроллер браузера на основе Playwright.
    
    Предоставляет async методы для управления браузером:
    запуск, навигация, взаимодействие с элементами.
    
    Attributes:
        config: Конфигурация браузера
        playwright: Экземпляр Playwright
        browser: Экземпляр браузера
        context: Контекст браузера (хранит cookies, localStorage)
        page: Активная страница
    
    Example:
        ```python
        controller = BrowserController()
        await controller.launch()
        await controller.navigate("https://example.com")
        await controller.click("button#submit")
        await controller.close()
        ```
    """
    
    def __init__(self, config: Optional[BrowserConfig] = None):
        """
        Инициализирует контроллер браузера.
        
        Args:
            config: Конфигурация браузера. Если не указана,
                   используется глобальная конфигурация.
        """
        self.config = config or get_config().browser
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        
        # P1 FIX: URL Validator для безопасности
        self._url_validator = URLValidator()
        
    @property
    def page(self) -> Optional[Page]:
        """Возвращает активную страницу."""
        return self._page
    
    @property
    def context(self) -> Optional[BrowserContext]:
        """Возвращает контекст браузера."""
        return self._context
    
    async def launch(self) -> Page:
        """
        Запускает браузер в видимом режиме.
        
        Создаёт persistent context для сохранения сессий
        между запусками.
        
        Returns:
            Page: Активная страница браузера
            
        Raises:
            BrowserError: Если не удалось запустить браузер
        """
        try:
            logger.info(f"Запуск браузера: {self.config.browser_type}")
            
            self._playwright = await async_playwright().start()
            
            # Выбираем тип браузера
            browser_type = getattr(
                self._playwright,
                self.config.browser_type,
                self._playwright.chromium
            )
            
            # Создаём директорию для данных пользователя
            user_data_dir = Path(self.config.user_data_dir)
            user_data_dir.mkdir(parents=True, exist_ok=True)
            
            # Browser args to enable extensions and hide automation
            browser_args = [
                "--disable-blink-features=AutomationControlled",  # Hide automation detection
                "--enable-extensions",  # Enable extensions
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",  # Hide "Chrome is being controlled by automated test software"
                "--no-first-run",
                "--no-default-browser-check",
                "--log-level=3",  # Suppress console warnings (0=INFO, 1=WARNING, 2=LOG, 3=ERROR only)
                "--silent-debugger-extension-api",  # Suppress debugger extension warnings
            ]
            
            # Flags to remove from default Playwright args (they block extensions)
            ignore_default_args = [
                "--enable-automation",  # Removes automation detection
                "--disable-extensions",  # We want extensions enabled
                "--disable-component-extensions-with-background-pages",  # Allow extension background pages
            ]
            
            # Запускаем persistent context для сохранения сессий
            self._context = await browser_type.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=self.config.headless,
                viewport={
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height
                },
                slow_mo=self.config.slow_mo,
                args=browser_args,
                ignore_default_args=ignore_default_args,
            )
            
            # Получаем или создаём страницу
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = await self._context.new_page()
            
            # Устанавливаем таймауты
            self._page.set_default_timeout(self.config.default_timeout)
            self._page.set_default_navigation_timeout(self.config.navigation_timeout)
            # Navigate to blank page to avoid cached URL errors
            await self._page.goto("about:blank")
            
            # Handle new tabs - switch to them automatically
            def on_new_page(new_page: Page):
                async def handle_new_page():
                    try:
                        logger.info(f"New tab opened: {new_page.url}")
                        
                        # Check if page is still open before waiting
                        if new_page.is_closed():
                            logger.debug("New page was already closed, ignoring")
                            return
                        
                        await new_page.wait_for_load_state("domcontentloaded", timeout=10000)
                        
                        # Check again before updating reference
                        if not new_page.is_closed():
                            self._page = new_page
                            logger.info(f"Switched to new tab: {new_page.url}")
                        else:
                            logger.debug("Page closed during load, keeping current page reference")
                            
                    except PlaywrightTimeoutError:
                        # Timeout is not critical - page may still be usable
                        if not new_page.is_closed():
                            self._page = new_page
                            logger.warning(f"New tab load timeout, but switched anyway: {new_page.url}")
                        else:
                            logger.debug("Page closed during timeout, keeping current page reference")
                    except Exception as e:
                        # Page was likely closed by user, ignore gracefully
                        logger.debug(f"New page handler error (page likely closed): {e}")
                
                asyncio.create_task(handle_new_page())
            
            self._context.on("page", on_new_page)
            
            logger.info("Браузер успешно запущен")
            return self._page
            
        except PlaywrightError as e:
            logger.error(f"Ошибка запуска браузера: {e}")
            raise BrowserError(f"Не удалось запустить браузер: {e}") from e
    
    async def _human_delay(
        self,
        min_ms: int = 100,
        max_ms: int = 500,
        label: str = "action"
    ) -> None:
        """
        Add random human-like delay between actions.
        
        Args:
            min_ms: Minimum delay in milliseconds
            max_ms: Maximum delay in milliseconds
            label: Label for debug logging
        """
        delay_seconds = random.uniform(min_ms / 1000, max_ms / 1000)
        logger.debug(f"Human-like delay ({label}): {delay_seconds:.3f}s")
        await asyncio.sleep(delay_seconds)
    
    async def _move_mouse_humanlike(self, target_x: int, target_y: int) -> None:
        """
        Simulate human-like mouse movement towards target coordinates.
        
        Moves the mouse in small steps with micro-delays to mimic
        natural human mouse movement patterns.
        
        Args:
            target_x: Target X coordinate
            target_y: Target Y coordinate
        """
        try:
            # Get current viewport size for starting position
            viewport = self._page.viewport_size
            if not viewport:
                viewport = {"width": 1280, "height": 800}
            
            # Start from a random edge position or center
            start_x = random.randint(0, viewport["width"])
            start_y = random.randint(0, viewport["height"])
            
            # Number of steps for movement
            steps = random.randint(
                HumanLikeDelays.MOUSE_STEPS_MIN,
                HumanLikeDelays.MOUSE_STEPS_MAX
            )
            
            for i in range(steps):
                # Calculate intermediate position with some randomness
                progress = (i + 1) / steps
                # Add slight curve/randomness to path
                jitter_x = random.randint(-3, 3)
                jitter_y = random.randint(-3, 3)
                
                current_x = int(start_x + (target_x - start_x) * progress + jitter_x)
                current_y = int(start_y + (target_y - start_y) * progress + jitter_y)
                
                await self._page.mouse.move(current_x, current_y)
                
                # Micro-delay between movements
                delay_ms = random.uniform(
                    HumanLikeDelays.MOUSE_STEP_MIN / 1000,
                    HumanLikeDelays.MOUSE_STEP_MAX / 1000
                )
                await asyncio.sleep(delay_ms)
            
            # Final move to exact target
            await self._page.mouse.move(target_x, target_y)
            logger.debug(f"Mouse moved humanlike to ({target_x}, {target_y})")
            
        except PlaywrightError as e:
            # Mouse movement failure is not critical
            logger.debug(f"Human-like mouse movement failed (non-critical): {e}")
    
    async def navigate(self, url: str) -> str:
        """
        Переходит на указанный URL.
        
        Включает:
        - Валидацию URL (блокирует file://, javascript:// и т.д.)
        - Ожидание загрузки DOM
        - Ожидание network idle для стабильности
        - Глобальное отключение target="_blank" на всех ссылках
        - Human-like delay after navigation
        
        Args:
            url: URL для навигации
            
        Returns:
            str: Текущий URL после навигации
            
        Raises:
            NavigationError: Если навигация не удалась или URL опасен
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        
        # P1 FIX: Валидация URL перед навигацией
        try:
            self._url_validator.validate(url)
        except URLValidationError as e:
            logger.error(f"URL заблокирован: {url} - {e}")
            raise NavigationError(str(e)) from e
        
        try:
            logger.info(f"Навигация на: {url}")
            await self._page.goto(url, wait_until="domcontentloaded")
            
            # P0 FIX: Ожидание network idle после навигации
            try:
                await self._page.wait_for_load_state(
                    "networkidle",
                    timeout=Timeouts.NETWORK_IDLE
                )
            except PlaywrightTimeoutError:
                # Network idle таймаут не критичен - страница может иметь
                # постоянные соединения (websocket, polling)
                logger.debug(f"Network idle таймаут для {url}, продолжаем")
            
            # Globally disable target="_blank" on all links (including dynamic ones)
            await self._disable_target_blank_globally()
            
            # Human-like delay after navigation to simulate reading/processing
            await self._human_delay(
                HumanLikeDelays.NAVIGATE_MIN,
                HumanLikeDelays.NAVIGATE_MAX,
                "post-navigation"
            )
            
            current_url = self._page.url
            logger.info(f"Навигация завершена: {current_url}")
            return current_url
            
        except PlaywrightTimeoutError as e:
            logger.error(f"Таймаут навигации: {url}")
            raise NavigationError(f"Таймаут при переходе на {url}") from e
        except PlaywrightError as e:
            logger.error(f"Ошибка навигации: {e}")
            raise NavigationError(f"Ошибка навигации на {url}: {e}") from e
    
    async def click(
        self,
        selector: str,
        timeout: int = Timeouts.CLICK,
        retries: int = Retries.MAX_RETRIES,
        humanlike_mouse: bool = True
    ) -> None:
        """
        Выполняет клик по элементу с множественными fallback стратегиями.
        
        Стратегии (по порядку):
        1. Стандартный клик через Playwright locator
        2. Force click (игнорирует перекрытие другими элементами)
        3. JavaScript click (обход проблем с видимостью)
        4. XPath по тексту (для :has-text селекторов)
        5. Клик по координатам (последний fallback)
        
        Note:
            Автоматически удаляет target="_blank" с ссылок перед кликом,
            чтобы предотвратить открытие новых вкладок.
            Includes human-like delays before clicking to avoid bot detection.
        
        Args:
            selector: CSS, XPath селектор или Playwright-специфичный селектор
            timeout: Таймаут ожидания элемента (мс)
            retries: Количество попыток для каждой стратегии
            humanlike_mouse: Whether to simulate human-like mouse movement
            
        Raises:
            ElementNotFoundError: Если элемент не найден после всех стратегий
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        
        # Human-like delay before clicking
        await self._human_delay(
            HumanLikeDelays.CLICK_MIN,
            HumanLikeDelays.CLICK_MAX,
            "pre-click"
        )
        
        # Remove target="_blank" to prevent new tabs opening
        await self._remove_target_blank(selector)
        
        last_error: Exception | None = None
        
        # Стратегия 1: Стандартный клик с retry
        for attempt in range(retries):
            try:
                logger.debug(f"Клик по элементу: {selector} (попытка {attempt + 1}/{retries})")
                
                # Ожидаем появления элемента
                await self._page.wait_for_selector(
                    selector,
                    state="visible",
                    timeout=timeout
                )
                
                # Прокручиваем к элементу
                element = self._page.locator(selector).first
                await element.scroll_into_view_if_needed()
                await asyncio.sleep(0.15)  # Даём время на анимацию scroll
                
                # Optional: Human-like mouse movement to element
                if humanlike_mouse:
                    try:
                        box = await element.bounding_box()
                        if box:
                            target_x = int(box["x"] + box["width"] / 2)
                            target_y = int(box["y"] + box["height"] / 2)
                            await self._move_mouse_humanlike(target_x, target_y)
                    except PlaywrightError:
                        pass  # Mouse movement is optional
                
                # Пробуем обычный клик
                await element.click(timeout=3000)
                
                logger.debug(f"Клик выполнен: {selector}")
                return  # Успех - выходим
                
            except PlaywrightTimeoutError as e:
                last_error = e
                if attempt < retries - 1:
                    wait_time = Retries.BASE_DELAY * (Retries.MULTIPLIER ** attempt)
                    logger.warning(
                        f"Элемент не найден: {selector}, "
                        f"повтор через {wait_time}s ({attempt + 1}/{retries})"
                    )
                    await asyncio.sleep(wait_time)
                    
            except PlaywrightError as e:
                last_error = e
                logger.debug(f"Обычный клик не удался: {e}, пробуем force click")
                break  # Переходим к fallback стратегиям
        
        # Стратегия 2: Force click (игнорирует перекрытие)
        try:
            logger.debug(f"Попытка force click: {selector}")
            element = self._page.locator(selector).first
            await element.scroll_into_view_if_needed()
            await element.click(force=True, timeout=3000)
            logger.debug(f"Force click выполнен: {selector}")
            return
        except PlaywrightError as e:
            logger.debug(f"Force click не удался: {e}")
            last_error = e
        
        # Стратегия 3: JavaScript click
        try:
            logger.debug(f"Попытка JavaScript click: {selector}")
            js_result = await self._js_click(selector)
            if js_result:
                logger.debug(f"JavaScript click выполнен: {selector}")
                return
        except PlaywrightError as e:
            logger.debug(f"JavaScript click не удался: {e}")
            last_error = e
        
        # Стратегия 4: XPath по тексту (для :has-text селекторов)
        if ":has-text(" in selector:
            try:
                text = self._extract_text_from_selector(selector)
                if text:
                    logger.debug(f"Попытка XPath по тексту: '{text}'")
                    xpath_result = await self._click_by_text_xpath(text)
                    if xpath_result:
                        logger.debug(f"XPath click выполнен для текста: '{text}'")
                        return
            except PlaywrightError as e:
                logger.debug(f"XPath click не удался: {e}")
                last_error = e
        
        # Стратегия 5: Клик по координатам (если элемент найден)
        try:
            logger.debug(f"Попытка клика по координатам: {selector}")
            coords_result = await self._click_by_coordinates(selector)
            if coords_result:
                logger.debug(f"Клик по координатам выполнен: {selector}")
                return
        except PlaywrightError as e:
            logger.debug(f"Клик по координатам не удался: {e}")
            last_error = e
        
        # Все стратегии исчерпаны
        logger.error(f"Все стратегии клика исчерпаны для: {selector}")
        if isinstance(last_error, PlaywrightTimeoutError):
            raise ElementNotFoundError(f"Элемент не найден: {selector}") from last_error
        else:
            raise BrowserError(f"Ошибка при клике на {selector}: {last_error}") from last_error
    
    async def _js_click(self, selector: str) -> bool:
        """
        Выполняет клик через JavaScript.
        
        Args:
            selector: CSS селектор элемента
            
        Returns:
            bool: True если клик выполнен успешно
        """
        # Для Playwright-специфичных селекторов используем другой подход
        if ":has-text(" in selector or selector.startswith("//"):
            # Получаем элемент через Playwright и кликаем через JS
            try:
                element = self._page.locator(selector).first
                await element.evaluate("el => el.click()")
                return True
            except PlaywrightError:
                return False
        
        # Для обычных CSS селекторов
        escaped_selector = selector.replace("'", "\\'").replace('"', '\\"')
        result = await self._page.evaluate(f'''
            () => {{
                const el = document.querySelector('{escaped_selector}');
                if (el) {{
                    el.scrollIntoView({{behavior: 'instant', block: 'center'}});
                    el.click();
                    return true;
                }}
                return false;
            }}
        ''')
        return result
    
    def _extract_text_from_selector(self, selector: str) -> str:
        """
        Извлекает текст из :has-text() селектора.
        
        Args:
            selector: Селектор с :has-text()
            
        Returns:
            str: Извлечённый текст или пустая строка
        """
        import re
        match = re.search(r':has-text\(["\'](.+?)["\']\)', selector)
        if match:
            return match.group(1)
        return ""
    
    async def _click_by_text_xpath(self, text: str) -> bool:
        """
        Выполняет клик по XPath с поиском по тексту.
        
        Args:
            text: Текст для поиска
            
        Returns:
            bool: True если клик выполнен успешно
        """
        # Пробуем несколько вариантов XPath
        xpath_variants = [
            f'//*[normalize-space(text())="{text}"]',  # Точное совпадение
            f'//*[contains(text(), "{text}")]',  # Частичное совпадение
            f'//button[contains(., "{text}")]',  # Кнопка с текстом
            f'//a[contains(., "{text}")]',  # Ссылка с текстом
            f'//*[@aria-label="{text}"]',  # По aria-label
        ]
        
        for xpath in xpath_variants:
            try:
                element = await self._page.wait_for_selector(
                    xpath,
                    state="visible",
                    timeout=2000
                )
                if element:
                    await element.scroll_into_view_if_needed()
                    await element.click(force=True)
                    return True
            except PlaywrightTimeoutError:
                continue
            except PlaywrightError:
                continue
        
        return False
    
    async def _click_by_coordinates(self, selector: str) -> bool:
        """
        Выполняет клик по координатам центра элемента.
        
        Args:
            selector: Селектор элемента
            
        Returns:
            bool: True если клик выполнен успешно
        """
        try:
            element = self._page.locator(selector).first
            box = await element.bounding_box()
            if box:
                # Кликаем в центр элемента
                x = box["x"] + box["width"] / 2
                y = box["y"] + box["height"] / 2
                await self._page.mouse.click(x, y)
                return True
        except PlaywrightError:
            pass
        return False
    
    async def click_at_position(self, x: int, y: int, humanlike_mouse: bool = True) -> None:
        """
        Выполняет клик по указанным координатам на странице.
        
        Args:
            x: X координата
            y: Y координата
            humanlike_mouse: Whether to simulate human-like mouse movement
            
        Raises:
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        
        # Human-like delay before clicking
        await self._human_delay(
            HumanLikeDelays.CLICK_MIN,
            HumanLikeDelays.CLICK_MAX,
            "pre-click-position"
        )
        
        # Optional: Human-like mouse movement
        if humanlike_mouse:
            await self._move_mouse_humanlike(x, y)
        
        logger.debug(f"Клик по координатам: ({x}, {y})")
        await self._page.mouse.click(x, y)
        logger.debug(f"Клик по координатам выполнен: ({x}, {y})")
    
    async def type_text(
        self,
        selector: str,
        text: str,
        clear_first: bool = True,
        humanlike: bool = True
    ) -> None:
        """
        Вводит текст в элемент с имитацией человеческого ввода.
        
        Args:
            selector: CSS или XPath селектор элемента
            text: Текст для ввода
            clear_first: Очистить поле перед вводом
            humanlike: Use human-like typing with random delays per character
            
        Raises:
            ElementNotFoundError: Если элемент не найден
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        
        try:
            logger.debug(f"Ввод текста в: {selector}")
            
            await self._page.wait_for_selector(selector, state="visible")
            element = self._page.locator(selector).first
            
            if clear_first:
                await element.clear()
            
            if humanlike:
                # Human-like typing: character by character with random delays
                # Using press_sequentially for more natural input simulation
                delay_per_char = random.randint(
                    HumanLikeDelays.TYPE_MIN,
                    HumanLikeDelays.TYPE_MAX
                )
                await element.press_sequentially(text, delay=delay_per_char)
                logger.debug(
                    f"Текст введён (humanlike, ~{delay_per_char}ms/char) в: {selector}"
                )
            else:
                # Fast typing for non-sensitive scenarios
                await element.type(text, delay=50)
                logger.debug(f"Текст введён (fast) в: {selector}")
            
        except PlaywrightTimeoutError as e:
            logger.error(f"Элемент не найден: {selector}")
            raise ElementNotFoundError(f"Элемент не найден: {selector}") from e
        except PlaywrightError as e:
            logger.error(f"Ошибка ввода текста: {e}")
            raise BrowserError(f"Ошибка при вводе текста в {selector}: {e}") from e
    
    async def select_option(self, selector: str, value: str) -> None:
        """
        Выбирает опцию в select элементе.
        
        Args:
            selector: CSS или XPath селектор select элемента
            value: Значение или текст опции для выбора
            
        Raises:
            ElementNotFoundError: Если элемент не найден
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        
        try:
            logger.debug(f"Выбор опции '{value}' в: {selector}")
            
            await self._page.wait_for_selector(selector, state="visible")
            
            # Пробуем выбрать по value, затем по label
            try:
                await self._page.select_option(selector, value=value)
            except PlaywrightError:
                await self._page.select_option(selector, label=value)
            
            logger.debug(f"Опция выбрана: {value}")
            
        except PlaywrightTimeoutError as e:
            logger.error(f"Select элемент не найден: {selector}")
            raise ElementNotFoundError(f"Select не найден: {selector}") from e
        except PlaywrightError as e:
            logger.error(f"Ошибка выбора опции: {e}")
            raise BrowserError(f"Ошибка при выборе опции в {selector}: {e}") from e
    
    async def scroll(
        self,
        direction: Literal["up", "down", "left", "right"] = "down",
        amount: int = 500
    ) -> None:
        """
        Прокручивает страницу с human-like задержкой.
        
        Args:
            direction: Направление прокрутки (up, down, left, right)
            amount: Количество пикселей для прокрутки
            
        Raises:
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        
        # Human-like delay before scrolling
        await self._human_delay(
            HumanLikeDelays.SCROLL_MIN,
            HumanLikeDelays.SCROLL_MAX,
            "pre-scroll"
        )
        
        logger.debug(f"Прокрутка: {direction} на {amount}px")
        
        delta_x = 0
        delta_y = 0
        
        if direction == "down":
            delta_y = amount
        elif direction == "up":
            delta_y = -amount
        elif direction == "right":
            delta_x = amount
        elif direction == "left":
            delta_x = -amount
        
        await self._page.evaluate(
            f"window.scrollBy({delta_x}, {delta_y})"
        )
        
        logger.debug(f"Прокрутка выполнена: {direction}")
    
    async def wait_for(
        self, 
        selector: str, 
        timeout: int = 30000,
        state: Literal["attached", "detached", "visible", "hidden"] = "visible"
    ) -> bool:
        """
        Ожидает появления/исчезновения элемента.
        
        Args:
            selector: CSS или XPath селектор элемента
            timeout: Таймаут ожидания в миллисекундах
            state: Ожидаемое состояние элемента
            
        Returns:
            bool: True если элемент найден, False при таймауте
            
        Raises:
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        
        try:
            logger.debug(f"Ожидание элемента: {selector} (state={state})")
            await self._page.wait_for_selector(
                selector, 
                timeout=timeout,
                state=state
            )
            logger.debug(f"Элемент найден: {selector}")
            return True
            
        except PlaywrightTimeoutError:
            logger.debug(f"Таймаут ожидания элемента: {selector}")
            return False
    
    async def take_screenshot(
        self,
        full_page: bool = False,
        timeout: int = Timeouts.SCREENSHOT
    ) -> bytes:
        """
        Делает скриншот страницы с timeout и fallback.
        
        P0 FIX: Добавлен timeout и fallback на viewport-only при таймауте.
        
        Args:
            full_page: Захватить всю страницу или только viewport
            timeout: Таймаут для скриншота (мс)
            
        Returns:
            bytes: PNG изображение в байтах
            
        Raises:
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        
        logger.debug(f"Создание скриншота (full_page={full_page})")
        
        try:
            screenshot = await self._page.screenshot(
                full_page=full_page,
                type="png",
                timeout=timeout
            )
            logger.debug("Скриншот создан")
            return screenshot
            
        except PlaywrightTimeoutError:
            if full_page:
                # P0 FIX: Fallback на viewport-only скриншот
                logger.warning(
                    "Full page screenshot timed out, falling back to viewport only"
                )
                try:
                    screenshot = await self._page.screenshot(
                        full_page=False,
                        type="png",
                        timeout=Timeouts.SCREENSHOT_FALLBACK
                    )
                    logger.debug("Viewport скриншот создан (fallback)")
                    return screenshot
                except PlaywrightTimeoutError as e:
                    logger.error("Fallback screenshot также не удался")
                    raise BrowserError("Не удалось создать скриншот") from e
            else:
                raise BrowserError("Таймаут при создании скриншота")
    
    async def go_back(self) -> Optional[str]:
        """
        Возвращается на предыдущую страницу в истории.
        
        Returns:
            str | None: URL после навигации или None если история пуста
            
        Raises:
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        
        try:
            logger.debug("Навигация назад")
            await self._page.go_back(wait_until="domcontentloaded")
            current_url = self._page.url
            logger.debug(f"Вернулись на: {current_url}")
            return current_url
            
        except PlaywrightError as e:
            logger.warning(f"Не удалось вернуться назад: {e}")
            return None
    
    async def refresh(self) -> str:
        """
        Обновляет текущую страницу.
        
        Returns:
            str: URL после обновления
            
        Raises:
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        
        logger.debug("Обновление страницы")
        await self._page.reload(wait_until="domcontentloaded")
        current_url = self._page.url
        logger.debug(f"Страница обновлена: {current_url}")
        return current_url
    
    async def close(self) -> None:
        """
        Закрывает браузер и освобождает ресурсы.
        
        Безопасно закрывает все ресурсы в правильном порядке.
        """
        logger.info("Закрытие браузера")
        
        try:
            if self._context:
                await self._context.close()
                self._context = None
                self._page = None
                
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
                
            logger.info("Браузер закрыт")
            
        except PlaywrightError as e:
            logger.error(f"Ошибка при закрытии браузера: {e}")
    
    async def close_other_tabs(self) -> int:
        """
        Close all tabs except the current one.
        
        Returns:
            int: Number of tabs that were closed
            
        Raises:
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        
        closed = 0
        if self._context:
            for page in self._context.pages:
                if page != self._page:
                    try:
                        await page.close()
                        closed += 1
                    except PlaywrightError as e:
                        logger.warning(f"Failed to close tab: {e}")
        
        logger.info(f"Closed {closed} extra tabs")
        return closed
    
    async def get_tab_count(self) -> int:
        """
        Get current number of open tabs.
        
        Returns:
            int: Number of open tabs
            
        Raises:
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        
        if self._context:
            return len(self._context.pages)
        return 0
    
    async def new_tab(self, url: str = "about:blank") -> str:
        """
        Create a new tab and switch to it.
        
        Args:
            url: URL to open in the new tab (default: about:blank)
            
        Returns:
            str: URL of the new tab
            
        Raises:
            BrowserError: If browser is not launched or tab creation fails
        """
        if not self._context:
            raise BrowserError(
                "Браузер не запущен. Вызовите launch() перед использованием."
            )
        
        try:
            new_page = await self._context.new_page()
            self._page = new_page  # Switch to new tab
            
            if url and url != "about:blank":
                await new_page.goto(url, timeout=self.config.navigation_timeout)
            
            logger.info(f"Opened new tab: {new_page.url}")
            return new_page.url
        except PlaywrightError as e:
            logger.error(f"Failed to create new tab: {e}")
            raise BrowserError(f"Не удалось создать новую вкладку: {e}") from e
    
    async def _remove_target_blank(self, selector: str) -> None:
        """
        Remove target="_blank" attribute from element before clicking.
        
        This prevents new tabs from opening when clicking links.
        
        Args:
            selector: CSS or XPath selector of the element
        """
        try:
            # Handle different selector types
            if selector.startswith("//") or ":has-text(" in selector:
                # For XPath and Playwright-specific selectors, use locator
                element = self._page.locator(selector).first
                await element.evaluate('''(el) => {
                    if (el.tagName === 'A') {
                        el.removeAttribute('target');
                        el.setAttribute('target', '_self');
                    }
                    // Also check parent if element is inside a link
                    let parent = el.closest('a');
                    if (parent) {
                        parent.removeAttribute('target');
                        parent.setAttribute('target', '_self');
                    }
                }''')
            else:
                # For CSS selectors
                escaped_selector = selector.replace("'", "\\'").replace('"', '\\"')
                await self._page.evaluate(f'''(selector) => {{
                    const el = document.querySelector(selector);
                    if (el) {{
                        if (el.tagName === 'A') {{
                            el.removeAttribute('target');
                            el.setAttribute('target', '_self');
                        }}
                        // Also check parent if element is inside a link
                        let parent = el.closest('a');
                        if (parent) {{
                            parent.removeAttribute('target');
                            parent.setAttribute('target', '_self');
                        }}
                    }}
                }}''', selector)
            logger.debug(f"Removed target='_blank' from element: {selector}")
        except PlaywrightError as e:
            # Not critical - element might not be a link
            logger.debug(f"Could not remove target='_blank' (non-critical): {e}")
    
    async def _disable_target_blank_globally(self) -> None:
        """
        Globally disable target="_blank" on all links including dynamically added ones.
        
        This method:
        1. Removes target="_blank" from all existing links
        2. Sets up a MutationObserver to handle dynamically added links
        """
        try:
            await self._page.evaluate('''() => {
                // Remove target="_blank" from all existing links
                document.querySelectorAll('a[target="_blank"]').forEach(a => {
                    a.target = '_self';
                });
                
                // Handle dynamically added links with MutationObserver
                if (!window.__targetBlankObserver) {
                    window.__targetBlankObserver = new MutationObserver(mutations => {
                        mutations.forEach(m => {
                            m.addedNodes.forEach(node => {
                                if (node.nodeType === 1) {  // Element node
                                    // Check if the node itself is a link
                                    if (node.tagName === 'A' && node.target === '_blank') {
                                        node.target = '_self';
                                    }
                                    // Check child links
                                    if (node.querySelectorAll) {
                                        node.querySelectorAll('a[target="_blank"]').forEach(a => {
                                            a.target = '_self';
                                        });
                                    }
                                }
                            });
                        });
                    });
                    window.__targetBlankObserver.observe(document.body, {
                        childList: true,
                        subtree: true
                    });
                }
            }''')
            logger.debug("Global target='_blank' disabler injected")
        except PlaywrightError as e:
            logger.warning(f"Could not inject global target='_blank' disabler: {e}")
    
    def _ensure_page(self) -> None:
        """
        Проверяет, что страница доступна.
        
        Raises:
            BrowserError: Если браузер не запущен
        """
        if self._page is None:
            raise BrowserError(
                "Браузер не запущен. Вызовите launch() перед использованием."
            )
    
    async def get_current_url(self) -> str:
        """
        Возвращает текущий URL страницы.
        
        Returns:
            str: Текущий URL
            
        Raises:
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        return self._page.url
    
    async def get_page_title(self) -> str:
        """
        Возвращает заголовок текущей страницы.
        
        Returns:
            str: Заголовок страницы
            
        Raises:
            BrowserError: Если браузер не запущен
        """
        self._ensure_page()
        return await self._page.title()
    
    async def __aenter__(self) -> "BrowserController":
        """Поддержка async context manager."""
        await self.launch()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Закрытие при выходе из контекста."""
        await self.close()