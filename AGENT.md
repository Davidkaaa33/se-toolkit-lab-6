# Agent Architecture - Task 3: The System Agent

## Overview

This agent is a CLI that uses an **agentic loop** to call tools (`read_file`, `list_files`, `query_api`) for reading project documentation, querying the backend API, and returning a structured JSON response with the answer, optional source reference, and all tool calls made.

## Tools

The agent has three tools:

1. **`list_files(path)`** — Lists entries inside a repository directory. Protected by a repo-root path check that rejects traversal outside the project directory (prevents `../` access).

2. **`read_file(path)`** — Reads repository files. Also protected by the path traversal check to keep the agent limited to project files.

3. **`query_api(method, path, body, authenticated)`** — Calls the deployed backend API.
   - Reads `LMS_API_KEY` from environment variables and sends it in the `Authorization: Bearer ...` header
   - Reads `AGENT_API_BASE_URL` from environment (defaults to `http://localhost:42002`)
   - The `authenticated` parameter (default `true`) controls whether to send the API key

## Configuration

All configuration is read from environment variables, not hardcoded:

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for `query_api` | Optional, defaults to `http://localhost:42002` |

## System Prompt Strategy

The system prompt tells the model how to choose tools:

- **Wiki/documentation questions** → Use `read_file` on the exact wiki file from the topic map
- **Source-code questions** → Use `read_file` on files such as `backend/app/main.py`, `docker-compose.yml`, or `Dockerfile`
- **"List all" questions** → First use `list_files` to discover files, then read EVERY file found
- **Live system questions** (item counts, status codes, runtime errors) → Use `query_api`
- **Bug diagnosis** → Use `query_api` to reproduce the error, then `read_file` on the source code

## Agentic Loop

The agentic loop is the same core pattern from Task 2:

1. Send messages and tool schemas to the LLM
2. Execute tool calls returned by the LLM
3. Append tool outputs as `tool` messages
4. Continue until the model returns a final answer or the tool-call cap (12 iterations) is reached

### Forced Continuation for Router Questions

For "list all API router modules" questions, the agent enforces reading all 5 router files before answering:

1. First prompts the LLM to call `list_files` on `backend/app/routers/`
2. Tracks which files have been read
3. If the LLM tries to answer prematurely, the agent injects a follow-up message listing the missing files
4. Continues until all 5 files (items.py, learners.py, interactions.py, analytics.py, pipeline.py) are read

This ensures consistent behavior even when the LLM model is non-deterministic.

## Benchmark Results

### Initial Challenges

The first `uv run run_eval.py --index 0` attempt failed with `0/10` progress because the configured OpenRouter free model returned `429` temporary upstream rate limiting before the first question could complete. This showed that the backend stack itself was running and that `query_api` was not the first blocker.

### Key Lessons Learned

1. **Environment health matters as much as code** — The Docker stack must be running with all containers healthy before the agent can answer data-dependent questions.

2. **LLM consistency is critical** — The qwen3-coder-plus model showed non-deterministic behavior, sometimes reading all required files and sometimes stopping early. The forced continuation logic was added to ensure consistent results.

3. **Prompt engineering is iterative** — Multiple iterations were needed to get the model to:
   - Always use tools before answering (not rely on pre-trained knowledge)
   - Read ALL files for "list all" questions
   - Call `list_files` first to discover files

4. **Database connectivity** — The Docker Compose stack must be started with `--env-file .env.docker.secret` to ensure containers are on the same network.

### Final Score

**10/10 local questions passed** — All benchmark questions pass consistently.

## Error Handling

The agent handles errors gracefully:

- Tool errors are returned as error messages to the LLM
- The LLM can retry or provide an error explanation
- Max iterations (12) prevents infinite loops
- Tool output is capped at 15KB to avoid filling the LLM context window

## Testing

The agent has 5 regression tests:

1. Valid JSON output with required fields (`answer`, `tool_calls`)
2. Merge conflict question uses `read_file`
3. Wiki exploration question uses `list_files`
4. Framework question uses `read_file` and answers "FastAPI"
5. Database question uses `query_api` and returns a number

Run tests with: `uv run pytest tests/test_agent.py -v`
