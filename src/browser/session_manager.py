"""
SessionManager - управление persistent sessions.

Модуль для сохранения и загрузки состояния браузера:
- Cookies
- LocalStorage
- SessionStorage
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from playwright.async_api import BrowserContext, Page


logger = logging.getLogger(__name__)


class SessionError(Exception):
    """Ошибка работы с сессией."""
    pass


class SessionManager:
    """
    Менеджер сессий браузера.
    
    Сохраняет и восстанавливает состояние браузера:
    - Cookies для всех доменов
    - LocalStorage и SessionStorage
    
    Attributes:
        storage_dir: Директория для хранения сессий
    
    Example:
        ```python
        session_manager = SessionManager("./user_data/sessions")
        
        # Сохранение сессии
        await session_manager.save_session(context, "my_account")
        
        # Загрузка сессии
        await session_manager.load_session(context, "my_account")
        
        # Получение списка сессий
        sessions = await session_manager.list_sessions()
        ```
    """
    
    def __init__(self, storage_dir: str = "./user_data/sessions"):
        """
        Инициализирует менеджер сессий.
        
        Args:
            storage_dir: Путь к директории для хранения файлов сессий
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"SessionManager инициализирован: {self.storage_dir}")
    
    async def save_session(
        self, 
        context: BrowserContext, 
        name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Сохраняет текущую сессию браузера.
        
        Сохраняет:
        - Cookies со всех доменов
        - Storage state (localStorage)
        - Метаданные (время сохранения, описание)
        
        Args:
            context: Контекст браузера Playwright
            name: Имя сессии (без расширения)
            metadata: Дополнительные метаданные для сохранения
            
        Returns:
            Path: Путь к файлу сессии
            
        Raises:
            SessionError: Если не удалось сохранить сессию
        """
        try:
            logger.info(f"Сохранение сессии: {name}")
            
            # Получаем storage state (включает cookies и localStorage)
            storage_state = await context.storage_state()
            
            # Добавляем метаданные
            session_data = {
                "name": name,
                "created_at": datetime.now().isoformat(),
                "storage_state": storage_state,
                "metadata": metadata or {}
            }
            
            # Сохраняем в файл
            session_file = self.storage_dir / f"{name}.json"
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Сессия сохранена: {session_file}")
            return session_file
            
        except Exception as e:
            logger.error(f"Ошибка сохранения сессии {name}: {e}")
            raise SessionError(f"Не удалось сохранить сессию: {e}") from e
    
    async def load_session(
        self, 
        context: BrowserContext, 
        name: str
    ) -> bool:
        """
        Загружает сохранённую сессию.
        
        Восстанавливает cookies и другие данные из файла сессии.
        
        Args:
            context: Контекст браузера Playwright
            name: Имя сессии (без расширения)
            
        Returns:
            bool: True если сессия успешно загружена
            
        Raises:
            SessionError: Если сессия не найдена или повреждена
        """
        session_file = self.storage_dir / f"{name}.json"
        
        if not session_file.exists():
            logger.warning(f"Сессия не найдена: {name}")
            return False
        
        try:
            logger.info(f"Загрузка сессии: {name}")
            
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            storage_state = session_data.get("storage_state", {})
            
            # Загружаем cookies
            cookies = storage_state.get("cookies", [])
            if cookies:
                await context.add_cookies(cookies)
                logger.debug(f"Загружено {len(cookies)} cookies")
            
            # localStorage восстанавливается автоматически при использовании
            # storage_state в launch_persistent_context,
            # но мы можем вручную установить его для конкретных страниц
            
            logger.info(f"Сессия загружена: {name}")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Повреждённый файл сессии {name}: {e}")
            raise SessionError(f"Повреждённый файл сессии: {e}") from e
        except Exception as e:
            logger.error(f"Ошибка загрузки сессии {name}: {e}")
            raise SessionError(f"Не удалось загрузить сессию: {e}") from e
    
    async def restore_storage_to_page(
        self, 
        page: Page, 
        name: str
    ) -> bool:
        """
        Восстанавливает localStorage и sessionStorage для страницы.
        
        Используется после навигации на страницу для восстановления
        данных из сохранённой сессии.
        
        Args:
            page: Страница Playwright
            name: Имя сессии
            
        Returns:
            bool: True если данные восстановлены
        """
        session_file = self.storage_dir / f"{name}.json"
        
        if not session_file.exists():
            return False
        
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            storage_state = session_data.get("storage_state", {})
            origins = storage_state.get("origins", [])
            
            current_origin = await page.evaluate("window.location.origin")
            
            for origin_data in origins:
                if origin_data.get("origin") == current_origin:
                    local_storage = origin_data.get("localStorage", [])
                    
                    # Восстанавливаем localStorage
                    for item in local_storage:
                        key = item.get("name")
                        value = item.get("value")
                        if key and value:
                            await page.evaluate(
                                f"localStorage.setItem('{key}', '{value}')"
                            )
                    
                    logger.debug(f"Восстановлено {len(local_storage)} items localStorage")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка восстановления storage: {e}")
            return False
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        Возвращает список доступных сессий.
        
        Returns:
            List[Dict]: Список сессий с метаданными
        """
        sessions = []
        
        for session_file in self.storage_dir.glob("*.json"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                sessions.append({
                    "name": session_file.stem,
                    "file": str(session_file),
                    "created_at": data.get("created_at"),
                    "metadata": data.get("metadata", {}),
                    "cookies_count": len(
                        data.get("storage_state", {}).get("cookies", [])
                    )
                })
            except Exception as e:
                logger.warning(f"Не удалось прочитать сессию {session_file}: {e}")
                sessions.append({
                    "name": session_file.stem,
                    "file": str(session_file),
                    "error": str(e)
                })
        
        return sorted(sessions, key=lambda x: x.get("created_at", ""), reverse=True)
    
    def delete_session(self, name: str) -> bool:
        """
        Удаляет сохранённую сессию.
        
        Args:
            name: Имя сессии
            
        Returns:
            bool: True если сессия удалена
        """
        session_file = self.storage_dir / f"{name}.json"
        
        if not session_file.exists():
            logger.warning(f"Сессия для удаления не найдена: {name}")
            return False
        
        try:
            session_file.unlink()
            logger.info(f"Сессия удалена: {name}")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления сессии {name}: {e}")
            return False
    
    def session_exists(self, name: str) -> bool:
        """
        Проверяет существование сессии.
        
        Args:
            name: Имя сессии
            
        Returns:
            bool: True если сессия существует
        """
        session_file = self.storage_dir / f"{name}.json"
        return session_file.exists()
    
    def get_session_info(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о сессии.
        
        Args:
            name: Имя сессии
            
        Returns:
            Dict | None: Информация о сессии или None
        """
        session_file = self.storage_dir / f"{name}.json"
        
        if not session_file.exists():
            return None
        
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            storage_state = data.get("storage_state", {})
            
            return {
                "name": name,
                "file": str(session_file),
                "created_at": data.get("created_at"),
                "metadata": data.get("metadata", {}),
                "cookies_count": len(storage_state.get("cookies", [])),
                "origins_count": len(storage_state.get("origins", [])),
                "cookies_domains": list(set(
                    c.get("domain", "") for c in storage_state.get("cookies", [])
                ))
            }
        except Exception as e:
            logger.error(f"Ошибка чтения информации о сессии {name}: {e}")
            return None
    
    async def export_cookies(
        self, 
        context: BrowserContext, 
        domain: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Экспортирует cookies из контекста.
        
        Args:
            context: Контекст браузера
            domain: Опционально - фильтр по домену
            
        Returns:
            List[Dict]: Список cookies
        """
        cookies = await context.cookies()
        
        if domain:
            cookies = [c for c in cookies if domain in c.get("domain", "")]
        
        return cookies
    
    async def import_cookies(
        self, 
        context: BrowserContext, 
        cookies: List[Dict[str, Any]]
    ) -> int:
        """
        Импортирует cookies в контекст.
        
        Args:
            context: Контекст браузера
            cookies: Список cookies для импорта
            
        Returns:
            int: Количество импортированных cookies
        """
        if not cookies:
            return 0
        
        await context.add_cookies(cookies)
        logger.debug(f"Импортировано {len(cookies)} cookies")
        return len(cookies)