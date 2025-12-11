"""
Test script to extract information from Gmail inbox.
This will attempt to read the last 3 emails from Gmail.
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


async def test_gmail():
    """Test extracting emails from Gmail."""
    print("=" * 70)
    print("🌐 Browser Agent - Gmail Email Extraction Test")
    print("=" * 70)
    print()
    
    # Define callback for confirmations
    async def confirm_action(action: str, reason: str) -> bool:
        print(f"\n⚠️  Security Check:")
        print(f"   Action: {action}")
        print(f"   Reason: {reason}")
        
        # Auto-approve navigation and reading, ask for other actions
        if "переход" in action.lower() or "navigate" in action.lower():
            print(f"   ✓ Auto-approved (navigation)\n")
            return True
        elif "извлечение" in reason.lower() or "extraction" in reason.lower():
            print(f"   ✓ Auto-approved (data extraction)\n")
            return True
        
        response = input("   Разрешить? (y/n): ")
        return response.lower() in ('y', 'yes', 'д', 'да')
    
    # Define callbacks for progress
    async def on_action(action: str, params: dict):
        print(f"🔵 Action: {action}")
        if action == "navigate":
            print(f"   → URL: {params.get('url', 'N/A')}")
        elif action == "click":
            print(f"   → Target: {params.get('selector', params.get('element_index', 'N/A'))}")
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
        print("TASK: Получи информацию из последних 3 писем в Gmail")
        print("=" * 70 + "\n")
        
        print("⚠️  NOTE: You may need to log in to Gmail manually if not already logged in.")
        print("   The browser will stay open for you to interact if needed.\n")
        
        # Run the Gmail task
        task = "Перейди на mail.google.com, дождись загрузки почты и получи информацию из последних 3 писем: от кого, тему и краткое содержание каждого письма"
        
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
            print("EXTRACTED EMAIL DATA:")
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
    asyncio.run(test_gmail())