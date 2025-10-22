# Monster Mash Chatroom - Configuration Guide

## Environment Variables

All configuration uses environment variables with `__` for nesting (Pydantic Settings).

### Message Bus

```bash
# Backend selection
BUS__BACKEND=kafka              # or "in-memory" (default)

# Kafka brokers - Option 1: Numbered (recommended for multiple brokers)
BUS__KAFKA__BROKERS__0=localhost:29092
BUS__KAFKA__BROKERS__1=localhost:29093
BUS__KAFKA__BROKERS__2=localhost:29094

# Kafka brokers - Option 2: Comma-separated (simpler for single broker)
BUS__KAFKA__BROKERS=localhost:29092,localhost:29093

# Other Kafka settings
BUS__KAFKA__TOPIC=monster.chat     # Topic name (default: monster.chat)
BUS__NAMESPACE=monster-mash-chatroom    # Consumer group prefix
BUS__HISTORY_LIMIT=200             # Messages kept for new WebSocket clients
```

**Why two broker formats?**
- Numbered (`__0`, `__1`) is how Pydantic Settings handles lists from env vars
- Comma-separated is a convenience we added via custom validator
- Both work identically; use whichever you prefer

### LLM Configuration

```bash
# Demo vs LLM mode
DEMO_MODE=true                  # true = scripted responses, false = real LLM

# Default model for all personas
MODEL_ROUTING__DEFAULT_MODEL=gpt-4o-mini

# Per-persona model routing (JSON)
MODEL_ROUTING__PERSONA_MODEL_MAP='{"witch":"gpt-4","vampire":"claude-3-5-sonnet-20241022"}'

# API keys (LiteLLM auto-detects from standard names)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
AZURE_API_KEY=...
GEMINI_API_KEY=...
```

### Server

```bash
UVICORN_PORT=8000              # Only affects run.sh script
UVICORN_LOG_LEVEL=info         # debug, info, warning, error
```

## Example Configurations

### Local Development (Demo Mode)
```bash
# .env
DEMO_MODE=true
BUS__BACKEND=in-memory
```

### Local with Kafka (Demo Mode)
```bash
# .env
DEMO_MODE=true
BUS__BACKEND=kafka
BUS__KAFKA__BROKERS__0=localhost:29092
```

### Local Ollama (No API Keys Required)
```bash
# 1. Install Ollama: https://ollama.ai
# 2. Pull a model: ollama pull llama3.2
# 3. Start Ollama (runs on http://localhost:11434 by default)

# .env
DEMO_MODE=false
MODEL_ROUTING__DEFAULT_MODEL=ollama/llama3.2    # or ollama/mistral, ollama/phi3, etc.
BUS__BACKEND=in-memory           # or kafka if you want Kafka too
OLLAMA_API_BASE=http://localhost:11434  # optional, this is the default
```

**Available Ollama Models:**
- `llama3.2` - Meta's latest (small and fast)
- `mistral` - Great for reasoning
- `phi3` - Microsoft's efficient model
- `gemma2` - Google's Gemma
- Full list: https://ollama.ai/library

**Per-persona routing with Ollama:**
```bash
MODEL_ROUTING__PERSONA_MODEL_MAP='{
  "witch": "ollama/llama3.2",
  "vampire": "ollama/mistral",
  "ghost": "ollama/phi3"
}'
```

### Production-like (LLM Mode)
```bash
# .env
DEMO_MODE=false
BUS__BACKEND=kafka
BUS__KAFKA__BROKERS=kafka-1:9092,kafka-2:9092,kafka-3:9092
MODEL_ROUTING__DEFAULT_MODEL=gpt-4o
OPENAI_API_KEY=sk-...
BUS__HISTORY_LIMIT=500
```

### Multi-Model Setup
```bash
# .env
DEMO_MODE=false
BUS__BACKEND=kafka
BUS__KAFKA__BROKERS__0=localhost:29092
MODEL_ROUTING__DEFAULT_MODEL=gpt-4o-mini

# Route specific personas to better models
MODEL_ROUTING__PERSONA_MODEL_MAP='{
  "witch": "gpt-4",
  "vampire": "claude-3-5-sonnet-20241022",
  "ghost": "gpt-4o-mini",
  "werewolf": "gpt-4o-mini",
  "zombie": "claude-3-5-sonnet-20241022"
}'

OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

## Configuration Priority

1. Environment variables (highest priority)
2. `.env` file
3. Default values in code (lowest priority)

The `run.sh` script exports Kafka vars for its session, so they override `.env`.

## Troubleshooting Config

**Check current config:**
```bash
python -c "from monster_mash_chatroom.config import get_settings; import json; s=get_settings(); print(json.dumps(s.model_dump(), indent=2, default=str))"
```

**Verify Kafka broker parsing:**
```bash
# Should show list of brokers
python -c "from monster_mash_chatroom.config import get_settings; print(get_settings().bus.kafka.brokers)"
```

**Test LLM model routing:**
```bash
# Check which model each persona uses
python -c "from monster_mash_chatroom.config import get_settings; s=get_settings(); print({k: s.model_routing.for_persona(k) for k in ['witch','vampire','ghost','werewolf','zombie']})"
```
