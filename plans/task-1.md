# Task 1 Plan

## Goal

Build a minimal `agent.py` CLI that sends a user question to ChatGPT through an OpenAI-compatible chat completions API and prints a single JSON object to stdout with:

```json
{"answer": "...", "tool_calls": []}
```

## LLM Provider

- Provider: ChatGPT via an OpenAI-compatible API
- Model: configured through `.env.agent.secret`
- Credentials: loaded from `.env.agent.secret`, not hardcoded

## Agent Structure

`agent.py` will follow this flow:

1. Read the user question from the first command-line argument.
2. Load `LLM_API_KEY`, `LLM_API_BASE`, and `LLM_MODEL` from `.env.agent.secret`.
3. Create a minimal chat-completions request with a short system prompt and the user question.
4. Extract the text answer from the model response.
5. Print one JSON line to stdout containing `answer` and `tool_calls`.
6. Send debug or error information to stderr only.

## Error Handling

- If the question argument is missing, exit with an error and write the message to stderr.
- If required environment variables are missing, exit with an error and write the message to stderr.
- If the API request fails or times out, write the error to stderr and return a non-zero exit code.
- Keep stdout reserved for valid JSON output on success.

## Data Flow

User CLI input -> `agent.py` -> environment config -> LLM API request -> model response -> JSON output

## Testing Plan

Create one regression test that:

1. Runs `agent.py` as a subprocess.
2. Captures stdout.
3. Parses stdout as JSON.
4. Verifies that `answer` and `tool_calls` are present.
5. Verifies that `tool_calls` is an empty array for Task 1.

## Documentation Plan

Update `AGENT.md` to document:

- the purpose of the agent
- the chosen LLM provider
- required environment variables
- how to run the CLI
- the JSON output format
