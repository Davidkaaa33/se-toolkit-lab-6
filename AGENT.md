# Agent

This project includes a simple CLI agent in `agent.py`.

## How it works

The agent:

1. reads a question from the command line
2. loads LLM settings from `.env.agent.secret`
3. sends the question to ChatGPT through an OpenAI-compatible chat completions API
4. prints a JSON response to stdout

The JSON format is:

```json
{"answer": "...", "tool_calls": []}
```

For Task 1, `tool_calls` is always an empty array.

## LLM provider

- Provider: ChatGPT
- API style: OpenAI-compatible chat completions API
- Model: configured with `LLM_MODEL` in `.env.agent.secret`

## Configuration

Create `.env.agent.secret` and set:

```env
LLM_API_KEY=your_api_key
LLM_API_BASE=your_api_base
LLM_MODEL=your_model_name
```

## How to run

```bash
uv run agent.py "What does REST stand for?"
```

Example output:

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```
