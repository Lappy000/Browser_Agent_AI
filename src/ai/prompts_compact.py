"""
КОМПАКТНАЯ версия промптов - экономия токенов ~80%

ОПТИМИЗИРОВАНО для минимального расхода токенов.
"""

from typing import List, Dict, Any

# УЛЬТРА-КОМПАКТНЫЙ системный промпт
SYSTEM_PROMPT_COMPACT = """AI browser agent. ALWAYS call tool!

Tools: navigate(url), click(element_index), type_text(element_index,text), scroll(direction), complete_task(summary,result)

🚫 FORBIDDEN - WILL FAIL:
- selector="tr:has-text(...)" ❌
- selector="span:has-text(...)" ❌
- selector="div.class-name" ❌
- ANY custom selector ❌

✅ ONLY USE: click(element_index=N) where N is [N] from EL list

⚠️ CRITICAL RULES:
1. EVERY response = tool call
2. click/type: Use element_index ONLY from EL list!
3. For SEQUENTIAL items (emails, search results):
   - Item 1 = index [36] → Item 2 = index [37 or next] → Item 3 = index [38 or next]
   - After going BACK, use NEXT index, not the same!
   - In Gmail: email rows are [36], [37], [38]... (incrementing indices)
4. Result = actual DATA extracted
5. Max 4-6 steps
6. HORIZONTAL SCROLL MENUS (e.g., category tabs):
   - If you see elements like "Холодные напитки", "Завтраки" in a row with ◀▶ arrows
   - Some tabs may be HIDDEN (off-screen) until you click the arrow button!
   - First click the ARROW (◀ or ▶) several times to reveal hidden tabs
   - THEN click on the revealed tab
   - Error "элемент СКРЫТ за пределами экрана" = need to click arrow first!

For YouTube: clicking title starts playback - no need for play button!"""


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
    """Компактный промпт с достаточным контекстом.
    
    Баланс между экономией и функциональностью:
    - Больше элементов для сложных страниц
    - Достаточно текста для извлечения данных
    - ВАЖНО: История действий для памяти агента
    """
    
    # ТОП-40 элементов для лучшего охвата
    elements = interactive_elements[:40]
    
    # Компактный формат: idx|type|text|selector
    elem_lines = []
    for idx, el in enumerate(elements):
        text = el.get("text", "")[:60]  # Увеличено для полных заголовков писем
        selector = el.get("selector", "")[:60]
        tag = el.get("tag", "")[:3].upper()
        
        # Компактный формат без координат
        elem_lines.append(f"[{idx}]{tag}:{text}→{selector}")
    
    elements_str = "\n".join(elem_lines) if elem_lines else "No elements"
    
    # Последние 3 действия для лучшего контекста
    history = action_history[-3:] if action_history else []
    history_str = "→".join([h[:40] for h in history]) if history else "Start"
    
    # КРИТИЧНО: Формируем полную историю действий для памяти агента
    actions_str = ""
    click_count = 0
    if actions_taken and len(actions_taken) > 0:
        # Показываем ВСЕ действия (до 15) для полной памяти
        recent_actions = actions_taken[-15:]
        actions_str = "\n📋 DONE:" + " → ".join(recent_actions)
        # Подсчитываем количество кликов на разные элементы для подсказки
        click_count = sum(1 for a in recent_actions if a.startswith("click"))
    
    # Контент страницы - увеличен для извлечения данных
    if len(content) > 2500:
        content = content[:2500] + "..."
    
    # Подсказка для последовательного чтения
    sequential_hint = ""
    if click_count >= 2:
        sequential_hint = f"\n🔢 You've done {click_count} clicks. For next item, use NEXT element index!"
    
    # Компактный формат с достаточным контекстом И памятью действий
    return f"""TASK:{task}
IT:{iteration}/{max_iterations}|URL:{url[:80]}
{actions_str}{sequential_hint}

EL({len(elements)}):
{elements_str}

TXT:{content[:2000]}

HIST:{history_str}

Tool?"""
