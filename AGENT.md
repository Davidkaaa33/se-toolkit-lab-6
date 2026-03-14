# Agent Architecture - Task 3: The System Agent

This agent is a CLI that uses an **agentic loop** to call tools (`read_file`, `list_files`, `query_api`) for reading project documentation, querying the backend API, and returning a structured JSON response with the answer, optional source reference, and all tool calls made.

The current agent has three tools. `list_files(path)` lists entries inside the
repository, `read_file(path)` reads repository files, and `query_api(method,
path, body)` calls the deployed backend. The file tools are protected by a
repo-root path check that rejects traversal outside the project directory. This
prevents `../` access and keeps the agent limited to project files. The API
tool reads `LMS_API_KEY` from environment variables and sends it in the
`Authorization: Bearer ...` header. The backend base URL is not hardcoded. The
agent reads `AGENT_API_BASE_URL` from the environment and falls back to
`http://localhost:42002`.

The system prompt tells the model how to choose tools. Wiki questions should
use `list_files` and `read_file`. Source-code questions should use
`read_file` on files such as `backend/app/main.py`, `docker-compose.yml`, or
`Dockerfile`. Live system questions such as item counts, status codes, and
runtime endpoint failures should use `query_api`. The agentic loop is the same
core pattern from Task 2: send messages and tool schemas to the model, execute
tool calls, append tool outputs as `tool` messages, and continue until the
model returns a final answer or the tool-call cap is reached.

For Task 3, the most important lesson from the benchmark was that environment
health matters as much as the code. The first `uv run run_eval.py --index 0`
attempt failed with `0/10` progress because the configured OpenRouter free
model returned `429` temporary upstream rate limiting before the first
question could complete. That result showed that the backend stack itself was
running and that `query_api` was not the first blocker. The local regression
tests passed, including the `query_api` test with header verification, so the
remaining benchmark risk is provider availability and then prompt/tool-choice
quality once the LLM responds consistently.
