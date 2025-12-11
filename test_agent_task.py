"""
Test script to run Browser Agent with a simple task.
This demonstrates that all fixes are working correctly.
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


async def test_agent():
    """Run a simple test task."""
    print("=" * 60)
    print("🌐 Browser Agent Test")
    print("=" * 60)
    print()
    
    # Define callback for confirmations
    async def confirm_action(action: str, reason: str) -> bool:
        print(f"\n⚠️  Security Check:")
        print(f"   Action: {action}")
        print(f"   Reason: {reason}")
        print(f"   Auto-approving for test...\n")
        return True  # Auto-approve for test
    
    # Define callbacks for progress
    async def on_action(action: str, params: dict):
        print(f"🔵 Action: {action}")
        if action == "navigate":
            print(f"   → URL: {params.get('url', 'N/A')}")
        elif action == "click":
            print(f"   → Target: {params.get('selector', params.get('element_index', 'N/A'))}")
        elif action == "type_text":
            text = params.get('text', '')
            preview = text[:50] + "..." if len(text) > 50 else text
            print(f"   → Text: {preview}")
    
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
        
        print("\n" + "=" * 60)
        print("TASK: Перейди на google.com")
        print("=" * 60 + "\n")
        
        # Run a simple task
        result = await agent.run("Перейди на google.com")
        
        print("\n" + "=" * 60)
        print("RESULT")
        print("=" * 60)
        print(f"Status: {result.status.value}")
        print(f"Summary: {result.summary}")
        print(f"Actions: {result.actions_count}")
        
        # Выводим статистику токенов
        token_stats = agent.get_token_stats()
        if token_stats["total_tokens"] > 0:
            print(f"\n💰 Token Usage:")
            print(f"   Input:  {token_stats['input_tokens']:,} tokens")
            print(f"   Output: {token_stats['output_tokens']:,} tokens")
            print(f"   Total:  {token_stats['total_tokens']:,} tokens")
            print(f"   Cost:   ${token_stats['estimated_cost']:.4f}")
        
        if result.error:
            print(f"\nError: {result.error}")
        print()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nClosing browser...")
        await agent.stop()
        print("✅ Test completed!")


if __name__ == "__main__":
    asyncio.run(test_agent())