"""
Test script for job search automation on hh.ru.
Tests agent's ability to search for jobs and analyze vacancies.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

# Set UTF-8 encoding for Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, TypeError):
        import os
        os.system('chcp 65001 >nul 2>&1')

from src.core.agent import BrowserAgent
from src.security.security_layer import SecurityLayer


async def test_job_search():
    """Test job search on hh.ru."""
    print("=" * 70)
    print("💼 Browser Agent - Job Search Test (hh.ru)")
    print("=" * 70)
    print()
    
    # Define callback for confirmations
    async def confirm_action(action: str, reason: str) -> bool:
        print(f"\n⚠️  Security Check:")
        print(f"   Action: {action}")
        print(f"   Reason: {reason}")
        
        # Auto-approve navigation and reading
        if any(kw in action.lower() for kw in ["переход", "navigate", "чтение", "read", "извлеч", "extract"]):
            print(f"   ✓ Auto-approved (safe action)\n")
            return True
        
        # Ask for confirmation on response/application actions
        if any(kw in reason.lower() for kw in ["откликн", "respond", "отправ", "send", "submit"]):
            print(f"   ⚠️  This will send a job application!")
            response = input("   Разрешить отправку отклика? (y/n): ")
            return response.lower() in ('y', 'yes', 'д', 'да')
        
        # Default: auto-approve
        print(f"   ✓ Auto-approved\n")
        return True
    
    # Define callbacks for progress
    async def on_action(action: str, params: dict):
        print(f"🔵 Action: {action}")
        if action == "navigate":
            print(f"   → URL: {params.get('url', 'N/A')}")
        elif action == "click":
            print(f"   → Target: {params.get('selector', params.get('element_index', 'N/A'))}")
        elif action == "type_text":
            text = params.get('text', '')
            preview = text[:30] + "..." if len(text) > 30 else text
            print(f"   → Text: {preview}")
        elif action == "extract_data":
            print(f"   → Query: {params.get('query', 'N/A')}")
    
    async def on_status(status: str):
        print(f"📝 Status: {status}")
    
    print("Initializing agent...")
    security = SecurityLayer(confirmation_callback=confirm_action)
    agent = BrowserAgent(
        on_action=on_action,
        on_status=on_status,
        security_layer=security
    )
    
    try:
        print("Starting browser...")
        await agent.start()
        
        print("\n" + "=" * 70)
        print("TASK: Найти вакансии AI-инженера на hh.ru")
        print("=" * 70 + "\n")
        
        print("⚠️  NOTE:")
        print("   - You should be logged in to hh.ru before running this")
        print("   - The agent will analyze vacancies but won't auto-apply")
        print("   - Browser will stay open for manual interaction if needed\n")
        
        # Job search task - analyze but don't auto-apply
        task = """Перейди на сайт hh.ru, найди через поиск 3 подходящие вакансии для AI-инженера или Python разработчика.
Для каждой вакансии извлеки:
- Название вакансии
- Название компании
- Зарплата (если указана)
- Ключевые требования
- Краткое описание

Предоставь краткий анализ: какие вакансии выглядят наиболее подходящими и почему.
НЕ откликайся на вакансии автоматически - только проанализируй."""
        
        result = await agent.run(task)
        
        print("\n" + "=" * 70)
        print("RESULT")
        print("=" * 70)
        print(f"Status: {result.status.value}")
        print(f"\nSummary: {result.summary}")
        print(f"\nActions performed: {result.actions_count}")
        
        # Token usage statistics
        token_stats = agent.get_token_stats()
        if token_stats["total_tokens"] > 0:
            print(f"\n💰 Token Usage:")
            print(f"   Input:  {token_stats['input_tokens']:,} tokens")
            print(f"   Output: {token_stats['output_tokens']:,} tokens")
            print(f"   Total:  {token_stats['total_tokens']:,} tokens")
            print(f"   Estimated Cost: ${token_stats['estimated_cost']:.4f}")
        
        if result.data:
            print(f"\n{'=' * 70}")
            print("FOUND VACANCIES:")
            print('=' * 70)
            print(result.data)
            print('=' * 70)
        
        if result.error:
            print(f"\n❌ Error: {result.error}")
        
        print()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\nPress Enter to close browser and exit...")
        print("Closing browser...")
        await agent.stop()
        print("✅ Test completed!")


if __name__ == "__main__":
    asyncio.run(test_job_search())