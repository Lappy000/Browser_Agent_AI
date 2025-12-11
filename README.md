# 🌐 Browser Agent AI

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Playwright](https://img.shields.io/badge/Playwright-1.49+-green.svg)](https://playwright.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An autonomous AI-powered browser agent that can execute complex multi-step web tasks without human intervention. Powered by Claude AI and Playwright.

## ✨ Features

- **🤖 Autonomous Task Execution** - Describe your task in natural language, and the agent figures out how to accomplish it
- **🌐 Full Browser Automation** - Navigation, clicks, form filling, text input, scrolling, and more
- **🧠 Intelligent Page Analysis** - Understands page structure without hardcoded selectors
- **👁️ Vision Mode** - Sends screenshots to AI for visual understanding of complex UIs
- **🔒 Security Layer** - Asks for confirmation before risky actions (payments, deletions, sensitive data)
- **💾 Persistent Sessions** - Saves login sessions between runs
- **🔌 Multiple LLM Providers** - Supports Anthropic Claude directly or via OpenRouter

## 📋 Example Tasks

```bash
# Search and research
"Go to google.com and find the weather in New York"

# Email management
"Read the last 10 emails in my inbox and delete spam"

# E-commerce
"Order a BBQ burger and fries from the place I ordered from last week"

# Job hunting
"Find 3 relevant AI engineer jobs on LinkedIn and apply to them"
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- API key from [Anthropic](https://console.anthropic.com/) or [OpenRouter](https://openrouter.ai/keys)

### Installation

```bash
# Clone the repository
git clone https://github.com/Lappy000/Browser_Agent_AI.git
cd Browser_Agent_AI

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Configuration

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your API key
# For OpenRouter:
#   OPENROUTER_API_KEY=your_key_here
# For Anthropic:
#   ANTHROPIC_API_KEY=your_key_here
```

### Running

**Windows:**
```bash
run.bat
```

**Linux/Mac:**
```bash
chmod +x run.sh
./run.sh
```

**Direct:**
```bash
python main.py
```

## 💡 Usage

After launching, you'll see the CLI interface:

```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║          🌐 Browser Agent v1.0                               ║
║                                                              ║
║      AI-powered browser automation                           ║
║      Powered by Claude AI & Playwright                       ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

Enter task: _
```

Simply describe what you want to accomplish, and the agent will execute it.

### Commands

| Command | Description |
|---------|-------------|
| `[task description]` | Execute a task |
| `help` | Show help |
| `status` | Current agent status |
| `stop` | Stop execution |
| `exit` / `quit` | Exit the program |

## 🛠️ Available Tools

The agent has access to these browser automation tools:

| Tool | Description |
|------|-------------|
| `navigate` | Go to a URL |
| `click` | Click on an element |
| `type_text` | Enter text into a field |
| `scroll` | Scroll the page up/down |
| `wait` | Wait for an element or time |
| `screenshot` | Capture the current page |
| `extract_text` | Get text content from elements |
| `get_page_info` | Get current page state |
| `done` | Mark task as complete |

## ⚙️ Configuration

All settings are in the `.env` file:

### LLM Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | AI provider (anthropic/openrouter) | `openrouter` |
| `OPENROUTER_API_KEY` | OpenRouter API key | - |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `LLM_MODEL` | Model to use | `anthropic/claude-sonnet-4` |
| `LLM_MAX_TOKENS` | Max tokens per response | `8096` |

### Security Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `SECURITY_ENABLED` | Enable security confirmations | `true` |

### Browser Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `BROWSER_TYPE` | Browser (chromium/firefox/webkit) | `chromium` |
| `HEADLESS` | Run without visible window | `false` |
| `VIEWPORT_WIDTH` | Browser window width | `1280` |
| `VIEWPORT_HEIGHT` | Browser window height | `800` |
| `DEFAULT_TIMEOUT` | Element wait timeout (ms) | `8000` |
| `NAVIGATION_TIMEOUT` | Page load timeout (ms) | `15000` |

### Vision Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `VISION_ENABLED` | Send screenshots to AI | `true` |
| `VISION_FREQUENCY` | When to capture (always/on_navigation/on_error) | `always` |

### Logging

| Variable | Description | Default |
|----------|-------------|---------|
| `SHOW_THINKING` | Show AI reasoning | `true` |
| `LOG_MODE` | Output mode (compact/verbose) | `verbose` |
| `LOG_LEVEL` | Log level | `INFO` |

## 🔒 Security

The agent asks for confirmation before potentially dangerous actions:

- 💳 **Payments** - Any financial transactions
- 🗑️ **Deletions** - Removing emails, files, records
- 📤 **Submissions** - Sending forms, posting content
- 🔐 **Sensitive Data** - Passwords, card details, personal info

When a risky action is detected:

```
╔══════════════════════════════════════════════════════════════╗
║                    🛡️ Security Check                         ║
╠══════════════════════════════════════════════════════════════╣
║  ⚠️  CONFIRMATION REQUIRED                                   ║
║                                                              ║
║  Action: Click on 'Pay Now' on shop.com/checkout             ║
║  Reason: Click on element with dangerous action (payment)    ║
║                                                              ║
║  Allow this action? [y/n]                                    ║
╚══════════════════════════════════════════════════════════════╝
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI                                  │
│                   (User Interface)                           │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    BrowserAgent                              │
│              (Main Agent Loop)                               │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │ TaskManager │ │ ContextMgr  │ │  SecurityLayer      │   │
│  └─────────────┘ └─────────────┘ └─────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│  BrowserCtrl  │ │  PageAnalyzer │ │   LLMClient   │
│  (Playwright) │ │  (DOM → LLM)  │ │  (Claude API) │
└───────────────┘ └───────────────┘ └───────────────┘
```

### Core Components

- **BrowserController** - Playwright browser management
- **PageAnalyzer** - DOM extraction and simplification for LLM
- **LLMClient** - Claude API interaction with function calling
- **BrowserAgent** - Main "think-act-observe" loop
- **TaskManager** - Task and iteration management
- **ContextManager** - Action history and context
- **SecurityLayer** - Dangerous action verification

## 📁 Project Structure

```
browser-agent/
├── src/
│   ├── browser/
│   │   ├── controller.py      # Playwright browser control
│   │   ├── page_analyzer.py   # DOM analysis and simplification
│   │   └── session_manager.py # Session persistence
│   ├── ai/
│   │   ├── llm_client.py      # LLM API client
│   │   ├── tools.py           # Function calling definitions
│   │   └── prompts.py         # System prompts
│   ├── core/
│   │   ├── agent.py           # Main agent class
│   │   ├── task_manager.py    # Task management
│   │   └── context_manager.py # History and context
│   ├── security/
│   │   ├── security_layer.py  # Security checks
│   │   └── url_validator.py   # URL validation
│   ├── ui/
│   │   └── cli.py             # CLI interface
│   └── config.py              # Configuration from .env
├── main.py                    # Entry point
├── requirements.txt           # Python dependencies
├── .env.example               # Example configuration
├── run.bat                    # Windows launch script
├── run.sh                     # Linux/Mac launch script
└── README.md                  # This file
```

## 🔧 Requirements

- **Python** 3.10+
- **Playwright** (installed via requirements.txt)
- **API Key** from Anthropic or OpenRouter

### Dependencies

```
anthropic>=0.40.0
playwright>=1.49.0
python-dotenv>=1.0.0
rich>=13.0.0
httpx>=0.27.0
```

## 🐛 Debugging

### Enable verbose logs

```env
LOG_LEVEL=DEBUG
```

### Slow down execution

```env
SLOW_MO=500
```

### Show browser window

```env
HEADLESS=false
```

## 🤝 How It Works

1. **User enters a task** in natural language
2. **Agent analyzes the page** - extracts simplified DOM
3. **LLM decides what to do** - chooses a tool and parameters
4. **SecurityLayer checks** - asks for confirmation if needed
5. **Action is executed** - click, type, navigate
6. **Loop repeats** until task is complete

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Anthropic Claude](https://www.anthropic.com/) - AI model
- [Playwright](https://playwright.dev/) - Browser automation
- [Rich](https://rich.readthedocs.io/) - Beautiful terminal UI