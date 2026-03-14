# Agent

This project includes a CLI documentation agent in `agent.py`.

## How it works

The agent:

1. reads a question from the command line
2. loads LLM settings from `.env.agent.secret`
3. sends the question, system prompt, and tool schemas to an OpenAI-compatible chat completions API
4. executes tool calls from the model
5. sends tool results back to the model
6. prints a JSON response to stdout

The JSON format is:

```json
{
  "answer": "...",
  "source": "wiki/file.md#section-anchor",
  "tool_calls": []
}
```

## Tools

The agent defines two tools:

- `list_files(path)` lists files and directories under a project path
- `read_file(path)` reads a file from the project

Both tools only allow paths inside the repository. Paths that try to escape the project directory are rejected.

## Agentic Loop

The agent uses a simple loop:

1. send the current conversation and tool schemas to the model
2. if the model asks for tools, execute them and append the results as `tool` messages
3. if the model returns a final text response, parse it and exit

The loop is capped at 10 tool calls.

## System Prompt Strategy

The system prompt tells the model to:

- answer using the repository wiki
- use `list_files` to discover wiki files
- use `read_file` to inspect documents
- return a final JSON object with `answer` and `source`

## Configuration

Create `.env.agent.secret` and set:

```env
LLM_API_KEY=your_api_key
LLM_API_BASE=your_api_base
LLM_MODEL=your_model_name
```

## How to run

```bash
uv run agent.py "What files are in the wiki?"
```
