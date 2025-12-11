"""Test input validation logic"""
import sys

# Set UTF-8 encoding for Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, TypeError):
        import os
        os.system('chcp 65001 >nul 2>&1')

# Test cases for input validation
ui_chars = set('═║╔╗╚╝─│┌┐└┘├┤┬┴┼▀▄█▌▐░▒▓■□▪▫')

test_inputs = [
    # (input, should_be_filtered, description)
    ("", True, "Empty input"),
    ("   ", True, "Whitespace only"),
    ("═══════", True, "Only UI chars"),
    ("║                                                              ║", True, "UI chars with spaces"),
    ("╔══════════════════════════════════════════════════════════════╗", True, "Box top"),
    ("проверь почту в гмаил", False, "Valid Russian task"),
    ("check email", False, "Valid English task"),
    ("go", True, "Too short (only 2 chars)"),
    ("xyz", False, "Short but valid (exactly 3 chars)"),
    ("a", True, "Too short (< 3 meaningful chars)"),
    ("═a═", True, "Mostly UI chars, too short meaningful content"),
    ("help", False, "Valid command"),
    ("status", False, "Valid command"),
    ("🌐", True, "Only emoji, too short"),
]

print("Testing input validation logic:\n")
for test_input, should_filter, description in test_inputs:
    # Check if empty
    if not test_input or not test_input.strip():
        filtered = True
    # Check if only UI chars
    elif all(c in ui_chars or c.isspace() for c in test_input):
        filtered = True
    else:
        # Remove UI chars and check meaningful length
        meaningful = ''.join(c for c in test_input if c not in ui_chars)
        meaningful = meaningful.strip()
        filtered = len(meaningful) < 3
    
    status = "✓" if filtered == should_filter else "✗"
    action = "FILTERED" if filtered else "ACCEPTED"
    
    display_input = test_input[:50] + "..." if len(test_input) > 50 else test_input
    print(f"{status} {action:8} | '{display_input}' - {description}")

print("\n✓ All tests passed!" if all(
    (not test_input or not test_input.strip() or 
     all(c in ui_chars or c.isspace() for c in test_input) or
     len(''.join(c for c in test_input if c not in ui_chars).strip()) < 3) == should_filter
    for test_input, should_filter, _ in test_inputs
) else "\n✗ Some tests failed!")