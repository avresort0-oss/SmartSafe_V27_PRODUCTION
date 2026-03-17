# AI Configuration Guide - SmartSafe V27

## Overview

SmartSafe V27 supports multiple AI providers with automatic fallback:

1. **LiteLLM Proxy** (Recommended) - Unified interface for multiple models
2. **Direct Blackbox AI** - Direct API calls to Blackbox
3. **Direct OpenAI** - Direct API calls to OpenAI
4. **Fallback Mode** - Heuristic-based analysis (no API key needed)

## Environment Variables

### Option 1: Using LiteLLM (Recommended)

```env
# Enable LiteLLM
LITELLM_ENABLED=true
LITELLM_PROXY_URL=http://localhost:4000
LITELLM_API_KEY=your_litellm_api_key

# Model configuration
LITELLM_MODEL=grok-fast

# API Keys (for the underlying models)
BLACKBOX_API_KEY=sk-oxYyDhHYX_Jj8vqgahXauw
OPENAI_API_KEY=
OPENROUTER_API_KEY=
```

### Option 2: Direct API Calls (No LiteLLM)

```env
# Use Blackbox directly
USE_BLACKBOX_API=true
BLACKBOX_API_KEY=sk-oxYyDhHYX_Jj8vqgahXauw

# Or use OpenAI
AI_API_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

## LiteLLM Configuration

Create a `litellm_config.yaml` file in the project root:

```yaml
model_list:
  # Primary model - grok-code-fast (free, fast)
  - model_name: grok-fast
    litellm_params:
      model: blackboxai/x-ai/grok-code-fast-1:free
      api_key: os.environ/BLACKBOX_API_KEY

  # Fallback 1 - blackbox-pro
  - model_name: blackbox-pro
    litellm_params:
      model: blackboxai/blackbox-pro
      api_key: os.environ/BLACKBOX_API_KEY

  # Fallback 2 - gpt-4o-mini
  - model_name: gpt-4o-mini
    litellm_params:
      model: gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEY

router_settings:
  routing_strategy: latency-based-routing
  cache: true
```

Start LiteLLM:

```bash
litellm --config litellm_config.yaml
```

## Error Resolution

### Error: "tool result's tool id not found"

This error occurs when:

1. The model tries to use tools/function calls that aren't registered
2. The request context is lost between calls
3. The model (e.g., minimax-m2-thinking) has issues with tool handling

**Solutions:**

1. **Disable tools for problematic models** - In your LiteLLM config, avoid using models that require tool definitions

2. **Use stable models** - Replace minimax with:
   - `grok-fast` (free, fast)
   - `blackbox-pro` (reliable)
   - `gpt-4o-mini` (fallback)

3. **Use direct API** - Set `USE_BLACKBOX_API=true` to bypass LiteLLM

## Testing

Test your AI configuration:

```python
from core.ai.ai_service import AIService

ai = AIService()
result = ai.analyze_message("Hello, I need help!")
print(result.sentiment, result.emotion)
```

## Troubleshooting

### No API Key

If no API key is configured, the system will use fallback mode with heuristic-based analysis.

### Rate Limiting

The service includes rate limiting (1 request per second). Increase with `min_request_interval` if needed.

### Timeout Issues

Increase timeout in the API calls if you experience slow responses.

## Model Recommendations

| Model | Pros | Cons |
|-------|------|------|
| grok-fast | Free, fast | Limited context |
| blackbox-pro | Reliable, good quality | Requires API key |
| gpt-4o-mini | OpenAI quality | Costs money |
| minimax-m2 | Thinking model | Has tool issues |
