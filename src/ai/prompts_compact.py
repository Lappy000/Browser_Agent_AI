"""
КОМПАКТНАЯ версия промптов - экономия токенов ~80%

ОПТИМИЗИРОВАНО для минимального расхода токенов.
"""

from typing import List, Dict, Any

# УЛЬТРА-КОМПАКТНЫЙ системный промпт
SYSTEM_PROMPT_COMPACT = """AI browser agent. ALWAYS call tool!

Tools: navigate(url), click(element_index), type_text(element_index,text), scroll(direction), complete_task(summary,result)

⚠️ CRITICAL RULES:
1. EVERY response = tool call
2. click/type: Use element_index [N] from EL list ONLY
3. DO NOT invent selectors from memory - use ONLY what's in EL list
4. If element not in list: scroll() to load more, or complete_task
5. Result = actual DATA, not description
6. Max 4-6 steps

For YouTube/video: clicking video title starts playback automatically - no need to find play button!"""


def _classify_element(el: dict) -> str:
    """Simple element type classification - NO semantic keyword matching.
    
    Classification is based ONLY on HTML tag and role attribute,
    NOT on text content or semantic keywords.
    """
    tag = el.get("tag", "").lower()
    attributes = el.get("attributes", {})
    role = attributes.get("role", "").lower()
    
    # Form inputs
    if tag == "input" or tag == "textarea":
        input_type = attributes.get("type", "").lower()
        return f"[INPUT:{input_type}]" if input_type else "[INPUT]"
    
    # Links
    if tag == "a":
        return "[LINK]"
    
    # Buttons
    if tag == "button" or role == "button":
        return "[BTN]"
    
    # Select dropdowns
    if tag == "select":
        return "[SELECT]"
    
    # Return uppercase tag name or generic [ELEM]
    return f"[{tag.upper()}]" if tag else "[ELEM]"


def build_task_prompt_compact(
    task: str,
    url: str,
    title: str,
    interactive_elements: List[Dict[str, Any]],
    content: str,
    action_history: List[str],
    iteration: int = 1,
    max_iterations: int = 25,
    actions_taken: List[str] = None
) -> str:
    """Ультра-компактный промпт для экономии токенов.
    
    Оптимизирован для минимального расхода:
    - Сокращённые элементы (только нужная инфо)
    - Минимум текста страницы
    - Краткая история
    """
    
    # ТОП-25 элементов (уменьшено с 40)
    elements = interactive_elements[:25]
    
    # Ультра-компактный формат: idx|type|text|selector
    elem_lines = []
    for idx, el in enumerate(elements):
        text = el.get("text", "")[:35]  # Уменьшено с 50
        selector = el.get("selector", "")[:45]  # Уменьшено с 60
        tag = el.get("tag", "")[:3].upper()
        
        # Компактный формат без координат (экономия ~20%)
        elem_lines.append(f"[{idx}]{tag}:{text}→{selector}")
    
    elements_str = "\n".join(elem_lines) if elem_lines else "No elements"
    
    # Только последние 2 действия
    history = action_history[-2:] if action_history else []
    history_str = "→".join([h[:30] for h in history]) if history else "Start"
    
    # Контент страницы - сильно урезан
    if len(content) > 600:  # Уменьшено с 1000
        content = content[:600] + "..."
    
    # Ультра-компактный формат
    return f"""TASK:{task}
IT:{iteration}/{max_iterations}|URL:{url[:60]}

EL({len(elements)}):
{elements_str}

TXT:{content[:400]}

HIST:{history_str}

Tool?"""
