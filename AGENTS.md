# AGENTS.md

## Environment Setup

```bash
conda activate ./venv
pip install -r requirements.txt
```

Copy `env.example` to `.env` and fill in your LLM API credentials.

## Running Scripts

| Command | Description |
|---------|-------------|
| `python main.py` | Placeholder welcome script |
| `python practice/llm_practice.py` | Basic LLM API calling |
| `python practice_02/chat_terminal.py` | Terminal chat with streaming |
| `python practice_02/tool_agent.py` | File operation tool agent (function calling) |
| `python practice_03/chat_summary.py` | Auto-summary when >5 turns or >3k tokens |
| `python practice_04/anythingllm_query.py` | AnythingLLM integration |
| `python practice_05/skill_agent.py` | Skill discovery and execution (reads .agent/skill/) |
| `python practice_06/tool_client.py` | Skill list via system prompt JSON + skill body loading |
| `python practice_07/tool_client.py` | Chained tool calling with context manager |

## Configuration (.env)

```env
BASE_URL=http://127.0.0.1:8080/v1  # or https://api.openai.com/v1
MODEL=                          # can be empty for local llama.cpp
API_KEY=                       # empty for local llama.cpp
MAX_TOKENS=500
CONTEXT_LENGTH=64000
```

## Directory Purposes

| Directory | Purpose |
|-----------|----------|
| `practice/` | Basic LLM API calling |
| `practice_02/` | Chat terminal + tool agent |
| `practice_03/` | Chat summary + context compression |
| `practice_04/` | AnythingLLM integration |
| `practice_05/` | Skill discovery and execution |
| `practice_06/` | Skill list via system prompt JSON + body loading |
| `practice_07/` | Chained tool calling with context manager |

## Notes

- No build/test/lint commands - run scripts directly with Python
- Uses OpenAI-compatible API format (works with Ollama, llama.cpp, OpenAI)
- practice_03 auto-summarizes: triggers after 5+ turns or >3k tokens in context