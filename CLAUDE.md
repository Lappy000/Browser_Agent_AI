# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Browser Agent - AI-агент для автономного управления веб-браузером. Использует Claude API (Anthropic) для принятия решений и Playwright для автоматизации браузера. Агент выполняет сложные многошаговые задачи на основе естественных языковых инструкций пользователя.

## Development Commands

### Initial Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Setup environment
cp .env.example .env
# Edit .env and add ANTHROPIC_API_KEY
```

### Running the Application
```bash
# Windows
run.bat

# Linux/Mac
chmod +x run.sh
./run.sh

# Direct execution
python main.py
```

### Environment Configuration
Required environment variables in `.env`:
- `ANTHROPIC_API_KEY` - Claude API key (required)
- `ANTHROPIC_MODEL` - Default: "claude-sonnet-4-20250514"
- `BROWSER_TYPE` - chromium/firefox/webkit (default: chromium)
- `HEADLESS` - true/false (default: false for visibility)
- `USER_DATA_DIR` - Path for browser sessions (default: ./user_data)
- `MAX_ITERATIONS` - Task iteration limit (default: 50)

See `.env.example` for all available options.

## High-Level Architecture

### Core Components

**BrowserAgent (src/core/agent.py)**
- Main agent loop implementing "think-act-observe" cycle
- Coordinates between AI decision engine, browser controller, and security layer
- Manages task lifecycle and iteration limits

**LLMClient (src/ai/llm_client.py)**
- Claude API integration using function calling
- Processes simplified page state and returns structured actions
- Tools defined in `src/ai/tools.py`

**BrowserController (src/browser/controller.py)**
- Playwright browser management with persistent context
- Handles browser lifecycle, page navigation, and event listeners
- Uses `user_data_dir` for session persistence (cookies, localStorage)

**PageAnalyzer (src/browser/page_analyzer.py)**
- **Critical component**: Simplifies full DOM to reduce token usage
- Extracts interactive elements (buttons, links, inputs) with positions
- Reduces 100k+ token pages to ~5-10k tokens while preserving semantic info
- Returns simplified state to LLM for decision making

**SecurityLayer (src/security/security_layer.py)**
- Intercepts potentially dangerous actions before execution
- Requires user confirmation for: payments, deletions, form submissions, personal data entry
- Pattern matching on action descriptions and URLs

**TaskManager (src/core/task_manager.py)**
- Manages task queue and execution flow
- Tracks iterations and prevents infinite loops

**ContextManager (src/core/context_manager.py)**
- Maintains conversation history between agent and LLM
- Optimizes context window usage (Claude's 100k token limit)

**CLI (src/ui/cli.py)**
- Rich-based terminal interface
- Displays agent status, actions, and security confirmations

### Data Flow

1. User provides task in natural language
2. BrowserController captures current page state
3. PageAnalyzer simplifies DOM to LLM-friendly format
4. LLMClient sends state + history to Claude, receives tool call
5. SecurityLayer checks action for dangerous patterns
6. If approved, BrowserController executes action
7. Loop continues until task complete or max iterations reached

### Key Design Patterns

**Autonomous Element Discovery**: No hardcoded selectors. PageAnalyzer extracts interactive elements with indices, LLM references by index or description, and BrowserController resolves at runtime using multiple strategies (text content, role, CSS selector, coordinates).

**Token Optimization**: Full HTML pages are simplified by:
- Removing invisible/script/style elements
- Flattening deep structures
- Truncating long text
- Extracting only interactive elements with key attributes
- Using indexed element references instead of full selectors

**Persistent Sessions**: Browser runs with `launch_persistent_context` and `user_data_dir`, preserving login state, cookies, and localStorage between runs.

**Function Calling Architecture**: All browser actions are exposed as tools to Claude API. LLM decides which tool to call based on task and page state. See `src/ai/tools.py` for complete tool definitions.

## Important Implementation Details

### Element Selection Strategy
When executing actions, the system tries multiple strategies in order:
1. Element index from interactive_elements list
2. Text content matching
3. ARIA role and name
4. CSS selector (AI-generated)
5. Coordinate-based clicking (fallback)

This is implemented in `BrowserController` action execution methods.

### Security Confirmation Flow
SecurityLayer uses pattern matching on:
- Action descriptions: "delete", "remove", "submit", "purchase", "buy", "send", "payment", "checkout"
- URLs: "bank", "payment", "checkout", "admin"

When detected, CLI displays confirmation dialog before proceeding. Never bypass security checks.

### System Prompt
The agent's behavior is defined by the system prompt in `src/ai/prompts.py`. This prompt:
- Instructs AI to analyze page state, not assume structure
- Emphasizes using element indices from interactive_elements
- Requires explicit task completion via `complete_task` tool
- Warns about sensitive actions

### Configuration Management
`src/config.py` loads all settings from environment variables. Use `Config.from_env()` to get current config. Default values are set for all optional settings.

## Common Development Patterns

### Adding New Browser Actions
1. Add tool definition to `BROWSER_TOOLS` in `src/ai/tools.py`
2. Implement handler in `BrowserController` (src/browser/controller.py)
3. Update system prompt if needed (src/ai/prompts.py)
4. Add security patterns if action is sensitive (src/security/security_layer.py)

### Modifying DOM Simplification
The `PageAnalyzer._simplify_dom()` method contains JavaScript executed in browser context. Adjust this to change what information is extracted. Balance between detail and token usage.

### Extending Security Rules
Edit `SecurityLayer` in `src/security/security_layer.py`:
- Add patterns to `DANGEROUS_PATTERNS`
- Add URL patterns to `SENSITIVE_URLS`
- Modify risk assessment logic in `_requires_confirmation()`

## Critical Files

- `src/browser/page_analyzer.py` - DOM simplification logic (affects LLM input quality)
- `src/ai/tools.py` - Browser action definitions (LLM's available actions)
- `src/ai/prompts.py` - System prompt (defines agent behavior)
- `src/core/agent.py` - Main agent loop (orchestrates everything)
- `src/config.py` - Configuration management (all settings)
- `src/security/security_layer.py` - Safety checks (prevents dangerous actions)

## Language Notes

This codebase uses Russian language for:
- Comments and docstrings
- User-facing messages in CLI
- System prompts (since typical users are Russian-speaking)

Code identifiers (variables, functions, classes) use English following Python conventions.
