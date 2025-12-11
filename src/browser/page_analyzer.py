"""
PageAnalyzer - извлечение и упрощение DOM для передачи в LLM.

Критически важный компонент, который:
- Извлекает интерактивные элементы с динамическими селекторами
- Упрощает DOM, удаляя ненужные элементы
- Ограничивает размер вывода для экономии токенов
- Захватывает скриншоты для vision режима LLM
"""

import base64
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from playwright.async_api import Page, Error as PlaywrightError

from ..constants import Limits, PageAnalysis


logger = logging.getLogger(__name__)


class PageAnalysisError(Exception):
    """Ошибка при анализе страницы."""
    pass


@dataclass
class InteractiveElement:
    """
    Интерактивный элемент страницы.
    
    Attributes:
        index: Уникальный индекс элемента на странице
        tag: HTML тег (button, a, input, и т.д.)
        element_type: Тип элемента (для input: text, password, и т.д.)
        text: Видимый текст элемента
        selector: Уникальный CSS/XPath селектор для идентификации
        attributes: Важные атрибуты (id, name, aria-label, и т.д.)
        position: Позиция элемента на странице (x, y) - центр элемента
        size: Размер элемента (width, height)
        is_visible: Видим ли элемент
        is_enabled: Доступен ли элемент для взаимодействия
        class_name: CSS классы элемента (для отладки)
        bounding_box: Полные координаты элемента (x, y, width, height)
    """
    index: int
    tag: str
    element_type: Optional[str] = None
    text: str = ""
    selector: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)
    position: Dict[str, int] = field(default_factory=dict)
    size: Dict[str, int] = field(default_factory=dict)
    is_visible: bool = True
    is_enabled: bool = True
    class_name: str = ""
    bounding_box: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует элемент в словарь с расширенной информацией."""
        return {
            "index": self.index,
            "tag": self.tag,
            "type": self.element_type,
            "text": self.text[:150] if self.text else "",  # Увеличено для полных названий
            "selector": self.selector,
            "attributes": self.attributes,
            "position": self.position,  # Центр элемента для click_at_coordinates
            "size": self.size,
            "is_visible": self.is_visible,
            "is_enabled": self.is_enabled,
            "class_name": self.class_name[:60] if self.class_name else "",
            "bounding_box": self.bounding_box  # Для точного позиционирования
        }


class PageAnalyzer:
    """
    Анализатор страниц для извлечения информации.
    
    Извлекает и упрощает DOM страницы для передачи в LLM,
    генерирует уникальные селекторы для каждого элемента.
    
    Attributes:
        max_dom_size: Максимальный размер упрощённого DOM в символах
        max_elements: Максимальное количество интерактивных элементов
    """
    
    def __init__(
        self,
        max_dom_size: int = Limits.MAX_DOM_SIZE,
        max_elements: int = Limits.MAX_ELEMENTS
    ):
        """
        Инициализирует анализатор.
        
        Args:
            max_dom_size: Макс. размер упрощённого DOM (символов)
            max_elements: Макс. количество интерактивных элементов
        """
        self.max_dom_size = max_dom_size
        self.max_elements = max_elements
    
    async def get_simplified_dom(self, page: Page) -> str:
        """
        Извлекает упрощённое представление DOM страницы.
        
        Удаляет:
        - script, style, noscript теги
        - Скрытые элементы (display: none, visibility: hidden)
        - Комментарии
        - SVG и canvas содержимое
        
        Сохраняет:
        - Интерактивные элементы (button, a, input, select, textarea)
        - Структурные элементы (header, main, footer, nav)
        - Текстовое содержимое
        
        Args:
            page: Страница Playwright
            
        Returns:
            str: Упрощённое HTML-подобное представление страницы
        """
        logger.debug("Извлечение упрощённого DOM")
        
        simplified_dom = await page.evaluate("""
            () => {
                // Проверка наличия document.body
                if (!document.body) {
                    return '<body>[Document body not available]</body>';
                }
                
                // Настройки
                const MAX_DEPTH = 6;
                const MAX_TEXT_LENGTH = 150;
                const MAX_CHILDREN = 20;
                
                // Теги для пропуска
                const SKIP_TAGS = new Set([
                    'script', 'style', 'noscript', 'svg', 'path',
                    'meta', 'link', 'head', 'template', 'iframe'
                ]);
                
                // Важные теги (приоритет при обрезке)
                const IMPORTANT_TAGS = new Set([
                    'button', 'a', 'input', 'select', 'textarea',
                    'form', 'h1', 'h2', 'h3', 'header', 'main',
                    'nav', 'footer', 'article', 'section'
                ]);
                
                function isVisible(element) {
                    if (!element) return false;
                    if (!element.offsetParent && element.tagName !== 'BODY') {
                        return false;
                    }
                    const style = window.getComputedStyle(element);
                    return style.display !== 'none' &&
                           style.visibility !== 'hidden' &&
                           style.opacity !== '0';
                }
                
                function getRelevantAttrs(element) {
                    if (!element) return '';
                    const attrs = [];
                    const relevantAttrs = [
                        'id', 'name', 'type', 'href', 'placeholder',
                        'aria-label', 'role', 'title', 'value', 'alt'
                    ];
                    
                    for (const attr of relevantAttrs) {
                        const value = element.getAttribute(attr);
                        if (value && value.length < 100) {
                            attrs.push(`${attr}="${value.substring(0, 50)}"`);
                        }
                    }
                    
                    // Добавляем первые 2 класса
                    if (element.className && typeof element.className === 'string') {
                        const classes = element.className.trim().split(/\\s+/).slice(0, 2);
                        if (classes.length > 0 && classes[0]) {
                            attrs.push(`class="${classes.join(' ')}"`);
                        }
                    }
                    
                    return attrs.join(' ');
                }
                
                function simplifyNode(node, depth = 0) {
                    // Null/undefined check - CRITICAL FIX for nodeType error
                    if (!node) return '';
                    
                    // Ограничение глубины
                    if (depth > MAX_DEPTH) return '';
                    
                    // Пропускаем текстовые узлы без контента
                    if (node.nodeType === Node.TEXT_NODE) {
                        const text = node.textContent?.trim() || '';
                        if (text.length > 0) {
                            return text.substring(0, MAX_TEXT_LENGTH);
                        }
                        return '';
                    }
                    
                    // Пропускаем не-элементы
                    if (node.nodeType !== Node.ELEMENT_NODE) return '';
                    
                    const tag = node.tagName?.toLowerCase();
                    if (!tag) return '';
                    
                    // Пропускаем ненужные теги
                    if (SKIP_TAGS.has(tag)) return '';
                    
                    // Проверяем видимость
                    if (!isVisible(node)) return '';
                    
                    const indent = '  '.repeat(depth);
                    const attrs = getRelevantAttrs(node);
                    const attrStr = attrs ? ' ' + attrs : '';
                    
                    // Собираем содержимое детей
                    const children = node.childNodes ? Array.from(node.childNodes) : [];
                    let childContent = [];
                    let childCount = 0;
                    
                    for (const child of children) {
                        if (childCount >= MAX_CHILDREN) {
                            childContent.push(`${indent}  ...и ещё ${children.length - childCount} элементов`);
                            break;
                        }
                        
                        const simplified = simplifyNode(child, depth + 1);
                        if (simplified) {
                            childContent.push(simplified);
                            childCount++;
                        }
                    }
                    
                    // Формируем вывод
                    const content = childContent.join('\\n');
                    
                    if (content) {
                        return `${indent}<${tag}${attrStr}>\\n${content}\\n${indent}</${tag}>`;
                    } else {
                        // Для пустых элементов показываем кратко
                        const text = node.textContent?.trim().substring(0, MAX_TEXT_LENGTH) || '';
                        if (text || IMPORTANT_TAGS.has(tag)) {
                            return `${indent}<${tag}${attrStr}>${text}</${tag}>`;
                        }
                        return '';
                    }
                }
                
                return simplifyNode(document.body);
            }
        """)
        
        # Обрезаем до максимального размера
        if len(simplified_dom) > self.max_dom_size:
            logger.debug(f"DOM обрезан с {len(simplified_dom)} до {self.max_dom_size}")
            simplified_dom = simplified_dom[:self.max_dom_size] + "\n... [обрезано]"
        
        logger.debug(f"Упрощённый DOM: {len(simplified_dom)} символов")
        return simplified_dom
    
    async def get_interactive_elements(self, page: Page) -> List[InteractiveElement]:
        """
        Возвращает список интерактивных элементов страницы.
        
        Для каждого элемента генерируется уникальный селектор
        на основе анализа DOM (без хардкода селекторов).
        
        Args:
            page: Страница Playwright
            
        Returns:
            List[InteractiveElement]: Список интерактивных элементов
        """
        logger.debug("Извлечение интерактивных элементов")
        
        elements_data = await page.evaluate("""
            () => {
                // Проверка наличия document.body - CRITICAL FIX for querySelectorAll error
                if (!document.body) {
                    return [];
                }
                
                const interactive = [];
                
                // Селекторы для интерактивных элементов (расширенный список с ARIA)
                const selectors = [
                    'a[href]',
                    'button',
                    'input:not([type="hidden"])',
                    'input[type="search"]',
                    'select',
                    'textarea',
                    '[onclick]',
                    '[role="button"]',
                    '[role="link"]',
                    '[role="menuitem"]',
                    '[role="tab"]',
                    '[role="checkbox"]',
                    '[role="radio"]',
                    '[role="combobox"]',
                    '[role="search"]',
                    '[role="searchbox"]',
                    '[role="listbox"]',
                    '[role="option"]',
                    '[role="spinbutton"]',
                    '[role="switch"]',
                    '[contenteditable="true"]',
                    '[tabindex]:not([tabindex="-1"])',
                    'details > summary'
                ];
                
                // Функция для проверки стабильности ID
                function isStableId(id) {
                    if (!id) return false;
                    // Динамические ID обычно содержат :, ;, ^ или выглядят как случайные строки
                    const dynamicPatterns = /[:;^]|^[a-z0-9]{1,3}$|^[0-9]+$/;
                    return !dynamicPatterns.test(id);
                }
                
                // Функция для генерации уникального селектора
                // Новый приоритет: aria-label → role → data-* → text → stable class → stable ID
                function generateSelector(element) {
                    // Приоритет 1: aria-label (самый стабильный)
                    const ariaLabel = element.getAttribute('aria-label');
                    if (ariaLabel && ariaLabel.length > 0 && ariaLabel.length < 100) {
                        const selector = `[aria-label="${CSS.escape(ariaLabel)}"]`;
                        const matches = document.querySelectorAll(selector);
                        if (matches.length === 1) {
                            return selector;
                        }
                        // Если не уникальный, комбинируем с тегом
                        const tagSelector = `${element.tagName.toLowerCase()}[aria-label="${CSS.escape(ariaLabel)}"]`;
                        const tagMatches = document.querySelectorAll(tagSelector);
                        if (tagMatches.length === 1) {
                            return tagSelector;
                        }
                    }
                    
                    // Приоритет 2: role атрибут + accessible name
                    const role = element.getAttribute('role');
                    if (role) {
                        // Попробуем role + aria-label
                        if (ariaLabel) {
                            const selector = `[role="${role}"][aria-label="${CSS.escape(ariaLabel)}"]`;
                            const matches = document.querySelectorAll(selector);
                            if (matches.length === 1) {
                                return selector;
                            }
                        }
                        // Попробуем role + текст
                        const text = element.textContent?.trim();
                        if (text && text.length > 0 && text.length < 50) {
                            const selector = `[role="${role}"]:has-text("${text.replace(/"/g, '\\\\"')}")`;
                            return selector;
                        }
                    }
                    
                    // Приоритет 3: data-* атрибуты (стабильные в тестах)
                    for (const attr of ['data-testid', 'data-qa', 'data-cy', 'data-test', 'data-action', 'data-id']) {
                        const value = element.getAttribute(attr);
                        if (value) {
                            const selector = `[${attr}="${CSS.escape(value)}"]`;
                            const matches = document.querySelectorAll(selector);
                            if (matches.length === 1) {
                                return selector;
                            }
                        }
                    }
                    
                    // Приоритет 4: комбинация тега + текста (для коротких текстов)
                    const text = element.textContent?.trim();
                    if (text && text.length > 0 && text.length < 50) {
                        const tag = element.tagName.toLowerCase();
                        // Для интерактивных элементов текст обычно стабилен
                        if (['button', 'a', 'span', 'div'].includes(tag)) {
                            return `${tag}:has-text("${text.replace(/"/g, '\\\\"')}")`;
                        }
                    }
                    
                    // Приоритет 5: name атрибут (для форм)
                    if (element.name) {
                        const selector = `${element.tagName.toLowerCase()}[name="${CSS.escape(element.name)}"]`;
                        const matches = document.querySelectorAll(selector);
                        if (matches.length === 1) {
                            return selector;
                        }
                    }
                    
                    // Приоритет 6: стабильные классы (не генерированные)
                    if (element.className && typeof element.className === 'string') {
                        const classes = element.className.trim().split(/\s+/);
                        // Ищем стабильные классы (не содержат цифры в конце, не слишком короткие)
                        const stableClasses = classes.filter(cls =>
                            cls.length > 3 &&
                            !/\d{2,}$/.test(cls) &&
                            !/-\d+$/.test(cls)
                        );
                        
                        if (stableClasses.length > 0) {
                            const classSelector = stableClasses.slice(0, 2).map(c => `.${CSS.escape(c)}`).join('');
                            const matches = document.querySelectorAll(classSelector);
                            if (matches.length === 1) {
                                return classSelector;
                            }
                        }
                    }
                    
                    // Приоритет 7: ТОЛЬКО стабильный ID (если выглядит стабильным)
                    if (element.id && isStableId(element.id)) {
                        const byId = document.querySelectorAll('#' + CSS.escape(element.id));
                        if (byId.length === 1) {
                            return '#' + CSS.escape(element.id);
                        }
                    }
                    
                    // Приоритет 6: nth-child путь от ближайшего элемента с ID
                    function getPathFromParentWithId(el) {
                        const path = [];
                        let current = el;
                        
                        while (current && current !== document.body) {
                            if (current.id) {
                                path.unshift('#' + CSS.escape(current.id));
                                return path.join(' > ');
                            }
                            
                            const parent = current.parentElement;
                            if (parent) {
                                const siblings = Array.from(parent.children);
                                const index = siblings.indexOf(current) + 1;
                                const tag = current.tagName.toLowerCase();
                                path.unshift(`${tag}:nth-child(${index})`);
                            }
                            current = parent;
                        }
                        
                        // Если нет ID, возвращаем путь от body
                        path.unshift('body');
                        return path.join(' > ');
                    }
                    
                    return getPathFromParentWithId(element);
                }
                
                // Проверка видимости
                function isVisible(el) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return false;
                    
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || 
                        style.visibility === 'hidden' ||
                        style.opacity === '0') return false;
                    
                    return true;
                }
                
                // Собираем все интерактивные элементы
                const allElements = document.querySelectorAll(selectors.join(','));
                
                allElements.forEach((el, index) => {
                    if (!isVisible(el)) return;
                    
                    const rect = el.getBoundingClientRect();
                    
                    // Пропускаем элементы вне viewport (с увеличенным запасом для scroll)
                    if (rect.bottom < -200 || rect.top > window.innerHeight + 500) return;
                    if (rect.right < -200 || rect.left > window.innerWidth + 200) return;
                    
                    // Получаем текст с приоритетом (улучшенное извлечение)
                    let elementText = '';
                    
                    // 1. aria-label (самый надёжный для кнопок и ссылок)
                    const ariaLabel = el.getAttribute('aria-label');
                    if (ariaLabel) {
                        elementText = ariaLabel;
                    }
                    // 2. title атрибут
                    else if (el.title) {
                        elementText = el.title;
                    }
                    // 3. innerText (получает ВСЕ видимый текст включая вложенные элементы)
                    else if (el.innerText && el.innerText.trim()) {
                        elementText = el.innerText.trim();
                    }
                    // 4. placeholder/value для инпутов
                    else if (el.placeholder) {
                        elementText = el.placeholder;
                    }
                    else if (el.value) {
                        elementText = el.value;
                    }
                    // 5. textContent как последний fallback
                    else {
                        elementText = el.textContent || '';
                    }
                    
                    elementText = elementText.trim().substring(0, 150);  // Увеличено с 100
                    
                    // Получаем классы
                    let className = '';
                    if (el.className && typeof el.className === 'string') {
                        className = el.className.trim().substring(0, 60);
                    }
                    
                    const info = {
                        index: interactive.length,
                        tag: el.tagName.toLowerCase(),
                        element_type: el.type || null,
                        text: elementText,
                        selector: generateSelector(el),
                        attributes: {},
                        position: {
                            x: Math.round(rect.x + rect.width / 2),
                            y: Math.round(rect.y + rect.height / 2)
                        },
                        size: {
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        },
                        is_visible: true,
                        is_enabled: !el.disabled,
                        class_name: className,
                        bounding_box: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        }
                    };
                    
                    // Расширенный список важных атрибутов
                    const attrsToCopy = [
                        'id', 'name', 'href', 'placeholder', 'aria-label',
                        'role', 'title', 'data-testid', 'data-qa', 'data-cy',
                        'data-action', 'data-id', 'alt', 'value'
                    ];
                    for (const attr of attrsToCopy) {
                        const value = el.getAttribute(attr);
                        if (value) {
                            info.attributes[attr] = value.substring(0, 100);
                        }
                    }
                    
                    interactive.push(info);
                });
                
                return interactive;
            }
        """)
        
        # Ограничиваем количество элементов
        if len(elements_data) > self.max_elements:
            logger.debug(f"Элементы обрезаны с {len(elements_data)} до {self.max_elements}")
            elements_data = elements_data[:self.max_elements]
        
        # Преобразуем в объекты InteractiveElement
        elements = [
            InteractiveElement(
                index=el["index"],
                tag=el["tag"],
                element_type=el.get("element_type"),
                text=el.get("text", ""),
                selector=el.get("selector", ""),
                attributes=el.get("attributes", {}),
                position=el.get("position", {}),
                size=el.get("size", {}),
                is_visible=el.get("is_visible", True),
                is_enabled=el.get("is_enabled", True),
                class_name=el.get("class_name", ""),
                bounding_box=el.get("bounding_box", {})
            )
            for el in elements_data
        ]
        
        logger.debug(f"Найдено {len(elements)} интерактивных элементов")
        return elements
    
    async def extract_text_content(self, page: Page) -> str:
        """
        Извлекает основной текстовый контент страницы.
        
        Фокусируется на:
        - Заголовках (h1-h6)
        - Параграфах (p)
        - Списках (li)
        - Статьях (article)
        
        Args:
            page: Страница Playwright
            
        Returns:
            str: Текстовое содержимое страницы
        """
        logger.debug("Извлечение текстового контента")
        
        text_content = await page.evaluate("""
            () => {
                // Проверка наличия document.body - CRITICAL FIX
                if (!document.body) {
                    return '[Document body not available]';
                }
                
                const MAX_LENGTH = 2000;  // Уменьшено с 5000 - экономия 60% токенов
                const textParts = [];
                
                // Ищем основной контент
                const mainContent = document.querySelector('main, article, [role="main"]') || document.body;
                
                // Извлекаем заголовки
                const headings = mainContent.querySelectorAll('h1, h2, h3, h4, h5, h6');
                headings.forEach(h => {
                    const text = h.textContent?.trim();
                    if (text) {
                        textParts.push(`[${h.tagName}] ${text}`);
                    }
                });
                
                // Извлекаем параграфы
                const paragraphs = mainContent.querySelectorAll('p');
                paragraphs.forEach(p => {
                    const text = p.textContent?.trim();
                    if (text && text.length > 20) {
                        textParts.push(text);
                    }
                });
                
                // Извлекаем элементы списков
                const listItems = mainContent.querySelectorAll('li');
                const listTexts = [];
                listItems.forEach(li => {
                    const text = li.textContent?.trim();
                    if (text && text.length > 10) {
                        listTexts.push('• ' + text.substring(0, 200));
                    }
                });
                if (listTexts.length > 0) {
                    textParts.push(listTexts.slice(0, 20).join('\\n'));
                }
                
                let result = textParts.join('\\n\\n');
                
                // Обрезаем если слишком длинный
                if (result.length > MAX_LENGTH) {
                    result = result.substring(0, MAX_LENGTH) + '\\n... [обрезано]';
                }
                
                return result;
            }
        """)
        
        logger.debug(f"Извлечено {len(text_content)} символов текста")
        return text_content
    
    async def get_page_state(
        self,
        page: Page,
        include_screenshot: bool = False,
        full_page: bool = False
    ) -> Dict[str, Any]:
        """
        Получает полное состояние страницы для передачи в LLM.
        
        P2 FIX: Улучшена обработка ошибок - специфичные exceptions
        вместо bare except, с детальным логированием.
        
        Args:
            page: Страница Playwright
            include_screenshot: Включить скриншот в base64 для vision режима
            full_page: Захватывать всю страницу (не только viewport)
            
        Returns:
            Dict: Состояние страницы включая URL, заголовок,
                  интерактивные элементы, упрощённый DOM и опционально скриншот
                  
        Note:
            Returns empty/default state if page is closed or unavailable.
        """
        logger.debug("Получение полного состояния страницы")
        
        # Check if page is closed before any operations
        if page.is_closed():
            logger.warning("Page is closed, returning empty state")
            return {
                "url": "",
                "title": "",
                "interactive_elements": [],
                "interactive_elements_count": 0,
                "simplified_dom": "",
                "text_content": "",
                "viewport": {
                    "width": PageAnalysis.DEFAULT_VIEWPORT_WIDTH,
                    "height": PageAnalysis.DEFAULT_VIEWPORT_HEIGHT
                },
                "screenshot_b64": None
            }
        
        # Собираем все данные параллельно где возможно
        try:
            url = page.url
        except PlaywrightError as e:
            logger.warning(f"Failed to get page URL (page likely closed): {e}")
            return {
                "url": "",
                "title": "",
                "interactive_elements": [],
                "interactive_elements_count": 0,
                "simplified_dom": "",
                "text_content": "",
                "viewport": {
                    "width": PageAnalysis.DEFAULT_VIEWPORT_WIDTH,
                    "height": PageAnalysis.DEFAULT_VIEWPORT_HEIGHT
                },
                "screenshot_b64": None
            }
        
        # Handle page navigation race condition with specific exceptions
        title = await self._safe_get_title(page)
        interactive_elements = await self._safe_get_interactive_elements(page)
        simplified_dom = await self._safe_get_simplified_dom(page)
        text_content = await self._safe_extract_text_content(page)
        viewport = await self._safe_get_viewport(page)
        
        # Capture screenshot for vision mode if requested
        screenshot_b64 = None
        if include_screenshot:
            screenshot_b64 = await self._safe_capture_screenshot(page, full_page)
        
        state = {
            "url": url,
            "title": title,
            "interactive_elements": [el.to_dict() for el in interactive_elements],
            "interactive_elements_count": len(interactive_elements),
            "simplified_dom": simplified_dom,
            "text_content": text_content,
            "viewport": viewport,
            "screenshot_b64": screenshot_b64
        }
        
        logger.debug(f"Состояние страницы: {url}, {len(interactive_elements)} элементов, screenshot={'yes' if screenshot_b64 else 'no'}")
        return state
    
    async def _safe_get_title(self, page: Page) -> str:
        """
        Безопасно получает заголовок страницы.
        
        Args:
            page: Страница Playwright
            
        Returns:
            str: Заголовок или пустая строка при ошибке
        """
        try:
            return await page.title()
        except PlaywrightError as e:
            logger.warning(f"Playwright error getting page title: {e}")
            return ""
        except TimeoutError as e:
            logger.warning(f"Timeout getting page title: {e}")
            return ""
    
    async def _safe_get_interactive_elements(
        self,
        page: Page
    ) -> List["InteractiveElement"]:
        """
        Безопасно получает интерактивные элементы.
        
        Args:
            page: Страница Playwright
            
        Returns:
            List[InteractiveElement]: Элементы или пустой список при ошибке
        """
        try:
            return await self.get_interactive_elements(page)
        except PlaywrightError as e:
            logger.warning(f"Playwright error getting interactive elements: {e}")
            return []
        except TimeoutError as e:
            logger.warning(f"Timeout getting interactive elements: {e}")
            return []
    
    async def _safe_get_simplified_dom(self, page: Page) -> str:
        """
        Безопасно получает упрощённый DOM.
        
        Args:
            page: Страница Playwright
            
        Returns:
            str: DOM или пустая строка при ошибке
        """
        try:
            return await self.get_simplified_dom(page)
        except PlaywrightError as e:
            logger.warning(f"Playwright error getting simplified DOM: {e}")
            return ""
        except TimeoutError as e:
            logger.warning(f"Timeout getting simplified DOM: {e}")
            return ""
    
    async def _safe_extract_text_content(self, page: Page) -> str:
        """
        Безопасно извлекает текстовый контент.
        
        Args:
            page: Страница Playwright
            
        Returns:
            str: Контент или пустая строка при ошибке
        """
        try:
            return await self.extract_text_content(page)
        except PlaywrightError as e:
            logger.warning(f"Playwright error extracting text content: {e}")
            return ""
        except TimeoutError as e:
            logger.warning(f"Timeout extracting text content: {e}")
            return ""
    
    async def _safe_get_viewport(self, page: Page) -> Dict[str, int]:
        """
        Безопасно получает размеры viewport.
        
        Args:
            page: Страница Playwright
            
        Returns:
            Dict[str, int]: Размеры viewport или дефолтные значения
        """
        try:
            return {
                "width": await page.evaluate("window.innerWidth"),
                "height": await page.evaluate("window.innerHeight")
            }
        except PlaywrightError as e:
            logger.warning(f"Playwright error getting viewport: {e}")
            return {
                "width": PageAnalysis.DEFAULT_VIEWPORT_WIDTH,
                "height": PageAnalysis.DEFAULT_VIEWPORT_HEIGHT
            }
        except TimeoutError as e:
            logger.warning(f"Timeout getting viewport: {e}")
            return {
                "width": PageAnalysis.DEFAULT_VIEWPORT_WIDTH,
                "height": PageAnalysis.DEFAULT_VIEWPORT_HEIGHT
            }
    
    async def _safe_capture_screenshot(
        self,
        page: Page,
        full_page: bool = False,
        use_jpeg: bool = True,
        jpeg_quality: int = 70,
        max_width: int = 1024,
        max_height: int = 768
    ) -> Optional[str]:
        """
        Безопасно захватывает скриншот и кодирует в base64.
        
        Оптимизирован для экономии токенов:
        - Поддержка JPEG сжатия (меньше размер = меньше токенов vision)
        - Resize до max_width/max_height
        
        Args:
            page: Страница Playwright
            full_page: Захватывать всю страницу (не только viewport)
            use_jpeg: Использовать JPEG вместо PNG (меньше размер)
            jpeg_quality: Качество JPEG (0-100)
            max_width: Максимальная ширина
            max_height: Максимальная высота
            
        Returns:
            str | None: Base64-encoded скриншот или None при ошибке
        """
        try:
            # Выбираем формат - JPEG значительно меньше PNG
            screenshot_type = "jpeg" if use_jpeg else "png"
            
            screenshot_bytes = await page.screenshot(
                type=screenshot_type,
                full_page=full_page,
                timeout=5000,  # 5 секунд таймаут
                quality=jpeg_quality if use_jpeg else None,
                scale="css"  # Используем CSS scale для оптимального размера
            )
            
            # Resize если нужно (для дополнительной экономии токенов)
            screenshot_bytes = await self._resize_screenshot_if_needed(
                screenshot_bytes,
                max_width,
                max_height,
                use_jpeg,
                jpeg_quality
            )
            
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            
            # Логируем экономию
            original_size = len(screenshot_bytes)
            b64_size = len(screenshot_b64)
            format_str = "JPEG" if use_jpeg else "PNG"
            logger.debug(
                f"Screenshot captured ({format_str}): {original_size:,} bytes "
                f"-> {b64_size:,} base64 chars"
            )
            
            return screenshot_b64
            
        except PlaywrightError as e:
            logger.warning(f"Playwright error capturing screenshot: {e}")
            return None
        except TimeoutError as e:
            logger.warning(f"Timeout capturing screenshot: {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error capturing screenshot: {e}")
            return None
    
    async def _resize_screenshot_if_needed(
        self,
        screenshot_bytes: bytes,
        max_width: int,
        max_height: int,
        use_jpeg: bool = True,
        jpeg_quality: int = 70
    ) -> bytes:
        """
        Resize скриншот если он больше указанных размеров.
        
        Использует PIL если доступен, иначе возвращает как есть.
        
        Args:
            screenshot_bytes: Исходные байты изображения
            max_width: Максимальная ширина
            max_height: Максимальная высота
            use_jpeg: Сохранять в JPEG
            jpeg_quality: Качество JPEG
            
        Returns:
            bytes: Обработанные байты изображения
        """
        try:
            from PIL import Image
            import io
            
            # Открываем изображение
            img = Image.open(io.BytesIO(screenshot_bytes))
            original_width, original_height = img.size
            
            # Проверяем нужен ли resize
            if original_width <= max_width and original_height <= max_height:
                return screenshot_bytes
            
            # Вычисляем новые размеры с сохранением пропорций
            ratio = min(max_width / original_width, max_height / original_height)
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)
            
            # Resize с высоким качеством
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Сохраняем в буфер
            buffer = io.BytesIO()
            if use_jpeg:
                # Конвертируем в RGB если нужно (JPEG не поддерживает alpha)
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                img.save(buffer, format='JPEG', quality=jpeg_quality, optimize=True)
            else:
                img.save(buffer, format='PNG', optimize=True)
            
            resized_bytes = buffer.getvalue()
            
            logger.debug(
                f"Screenshot resized: {original_width}x{original_height} -> "
                f"{new_width}x{new_height}, {len(screenshot_bytes):,} -> {len(resized_bytes):,} bytes"
            )
            
            return resized_bytes
            
        except ImportError:
            # PIL не установлен - возвращаем как есть
            logger.debug("PIL not available for screenshot resize, using original size")
            return screenshot_bytes
        except Exception as e:
            logger.warning(f"Error resizing screenshot: {e}, using original")
            return screenshot_bytes
    
    async def find_element_by_description(
        self, 
        page: Page, 
        description: str
    ) -> Optional[InteractiveElement]:
        """
        Находит элемент по текстовому описанию.
        
        Ищет среди интерактивных элементов тот, который
        лучше всего соответствует описанию (по тексту, 
        атрибутам, aria-label).
        
        Args:
            page: Страница Playwright
            description: Текстовое описание элемента
            
        Returns:
            InteractiveElement | None: Найденный элемент или None
        """
        description_lower = description.lower()
        elements = await self.get_interactive_elements(page)
        
        best_match = None
        best_score = 0
        
        for element in elements:
            score = 0
            
            # Проверяем текст элемента
            if element.text and description_lower in element.text.lower():
                score += 3
            
            # Проверяем атрибуты
            for attr, value in element.attributes.items():
                if value and description_lower in value.lower():
                    score += 2
            
            # Проверяем тег
            if element.tag in description_lower:
                score += 1
            
            if score > best_score:
                best_score = score
                best_match = element
        
        if best_match:
            logger.debug(f"Найден элемент по описанию '{description}': {best_match.selector}")
        else:
            logger.debug(f"Элемент не найден по описанию: {description}")
        
        return best_match