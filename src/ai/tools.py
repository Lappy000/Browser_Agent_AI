"""
Определения инструментов для Claude function calling.

Этот модуль содержит определения всех инструментов, которые
AI-агент может использовать для управления браузером.
"""

from typing import Optional, Dict, Any


BROWSER_TOOLS = [
    {
        "name": "navigate",
        "description": "Переход на указанный URL. Используйте для навигации на конкретную веб-страницу.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL страницы для перехода (например, https://example.com)"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "click",
        "description": "Клик по элементу. Используй element_index из списка EL или selector. ВАЖНО: Используй ТОЛЬКО индексы из текущего списка элементов, НЕ выдумывай селекторы из памяти!",
        "input_schema": {
            "type": "object",
            "properties": {
                "element_index": {
                    "type": "integer",
                    "description": "РЕКОМЕНДУЕТСЯ: Индекс [N] из списка EL (например, 5 для элемента [5])"
                },
                "selector": {
                    "type": "string",
                    "description": "CSS селектор. Используй ТОЛЬКО если элемента нет в списке. Предпочитай: aria-label, :has-text(), role"
                }
            },
            "required": []
        }
    },
    {
        "name": "click_at_coordinates",
        "description": "Клик по указанным координатам на странице. Используй когда обычный click по селектору не работает. Координаты можно взять из поля 'position' или 'bounding_box' интерактивного элемента.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {
                    "type": "integer",
                    "description": "X координата (пиксели от левого края viewport)"
                },
                "y": {
                    "type": "integer",
                    "description": "Y координата (пиксели от верхнего края viewport)"
                },
                "element_index": {
                    "type": "integer",
                    "description": "Индекс элемента из списка interactive_elements (координаты будут взяты из position)"
                }
            },
            "required": []
        }
    },
    {
        "name": "type_text",
        "description": "Ввод текста в поле ввода. Сначала кликните на поле, затем введите текст.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS селектор поля ввода"
                },
                "element_index": {
                    "type": "integer",
                    "description": "Индекс элемента из списка interactive_elements"
                },
                "text": {
                    "type": "string",
                    "description": "Текст для ввода в поле"
                },
                "clear": {
                    "type": "boolean",
                    "description": "Очистить поле перед вводом (по умолчанию true)",
                    "default": True
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "select_option",
        "description": "Выбор опции в выпадающем списке (select элемент).",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS селектор select элемента"
                },
                "element_index": {
                    "type": "integer",
                    "description": "Индекс select элемента из списка interactive_elements"
                },
                "value": {
                    "type": "string",
                    "description": "Значение или видимый текст опции для выбора"
                }
            },
            "required": ["value"]
        }
    },
    {
        "name": "scroll",
        "description": "Прокрутка страницы для просмотра дополнительного контента.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "left", "right"],
                    "description": "Направление прокрутки"
                },
                "amount": {
                    "type": "string",
                    "enum": ["small", "medium", "large", "page"],
                    "description": "Величина прокрутки (по умолчанию medium)",
                    "default": "medium"
                }
            },
            "required": ["direction"]
        }
    },
    {
        "name": "wait",
        "description": "Ожидание загрузки страницы или появления элемента. ИСПОЛЬЗУЙ ТОЛЬКО когда действительно нужно дождаться загрузки. Большинство действий не требуют wait. ИСПОЛЬЗУЙ минимальные значения: 200-500ms. Значения >1000ms только для очень медленных страниц.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS селектор элемента для ожидания (опционально)"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Максимальное время ожидания в миллисекундах (по умолчанию 500ms для скорости). Используй 200-500ms для большинства случаев.",
                    "default": 500
                }
            },
            "required": []
        }
    },
    {
        "name": "extract_data",
        "description": "Извлечение данных со страницы. ВАЖНО: После извлечения данных НЕМЕДЛЕННО вызови complete_task и передай отформатированные данные пользователю в поле 'result'. НЕ оставляй данные только в этом инструменте - пользователь должен их увидеть!",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Описание данных для извлечения (например, 'последние 10 писем', 'все цены товаров', 'текст статьи')"
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "list", "json"],
                    "description": "Желаемый формат вывода (по умолчанию text)",
                    "default": "text"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "go_back",
        "description": "Возврат на предыдущую страницу в истории браузера.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "refresh",
        "description": "Обновление текущей страницы.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "take_screenshot",
        "description": "Создание скриншота текущей страницы для визуального анализа. ИСПОЛЬЗУЙ ТОЛЬКО когда действительно нужно увидеть страницу для принятия решения. НЕ делай скриншоты после каждого действия.",
        "input_schema": {
            "type": "object",
            "properties": {
                "full_page": {
                    "type": "boolean",
                    "description": "Захватить всю страницу или только видимую область (по умолчанию false)",
                    "default": False
                }
            }
        }
    },
    {
        "name": "complete_task",
        "description": """ОБЯЗАТЕЛЬНАЯ функция для завершения задачи.

⚠️ КРИТИЧЕСКИ ВАЖНО для задач извлечения данных:
- result должен содержать САМИ ДАННЫЕ (письма, информацию, список), НЕ описание процесса
- result НЕ должен быть описанием вроде "Извлечены данные" или "Проанализированы письма"
- result должен быть отформатирован для чтения пользователем с нумерацией и структурой

НЕПРАВИЛЬНО ❌:
result="Проанализированы последние письма в Gmail"

ПРАВИЛЬНО ✅:
result=\"\"\"Последние 10 писем:

1. От: example@mail.com
   Тема: Important Update
   Дата: 2024-01-01
   Содержание: Brief summary of email content...
   
2. От: another@mail.com
   Тема: Meeting Request
   Дата: 2024-01-02
   Содержание: Another brief summary...
   
...
\"\"\"

Используй когда задача завершена. При извлечении данных ОБЯЗАТЕЛЬНО заполняй result с ФАКТИЧЕСКИМИ данными.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Была ли задача выполнена успешно"
                },
                "summary": {
                    "type": "string",
                    "description": "Краткое описание выполненных действий (например, 'Извлечено 10 писем из Gmail')"
                },
                "result": {
                    "type": "string",
                    "description": "⚠️ ОБЯЗАТЕЛЬНОЕ поле для извлечённых данных! Должно содержать ФАКТИЧЕСКИЕ ДАННЫЕ (не описание процесса). Форматируй четко и структурированно: для emails - тема, отправитель, дата, содержание каждого письма; для товаров - название, цена, описание; для статей - полный текст или резюме. Используй нумерацию (1., 2., 3.) и разделители (\\n\\n) для читабельности."
                }
            },
            "required": ["success", "summary"]
        }
    },
    {
        "name": "ask_user",
        "description": "Задать вопрос пользователю для уточнения. Используйте если нужна дополнительная информация.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Вопрос к пользователю"
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Варианты ответов (опционально)"
                }
            },
            "required": ["question"]
        }
    },
    {
        "name": "new_tab",
        "description": "Открыть новую вкладку и переключиться на неё. Используй перед navigate если нужно сохранить текущую страницу (например, музыка играет на YouTube).",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL для открытия в новой вкладке (опционально, по умолчанию about:blank)"
                }
            },
            "required": []
        }
    }
]


def get_tool_by_name(name: str) -> Optional[Dict[str, Any]]:
    """
    Получает определение инструмента по имени.
    
    Args:
        name: Имя инструмента
        
    Returns:
        Dict | None: Определение инструмента или None если не найден
    """
    for tool in BROWSER_TOOLS:
        if tool["name"] == name:
            return tool
    return None


def get_all_tool_names() -> list[str]:
    """
    Возвращает список имён всех доступных инструментов.
    
    Returns:
        list[str]: Список имён инструментов
    """
    return [tool["name"] for tool in BROWSER_TOOLS]


# Маппинг размера прокрутки
SCROLL_AMOUNTS = {
    "small": 200,
    "medium": 500,
    "large": 1000,
    "page": -1  # Специальное значение для прокрутки на высоту viewport
}