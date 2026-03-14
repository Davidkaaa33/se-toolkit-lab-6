# Task 3 Plan

## Goal

Extend the Task 2 documentation agent into a system agent by adding a `query_api`
tool. The updated agent should answer:

- wiki questions with `read_file` and `list_files`
- source-code questions with `read_file`
- live system and data questions with `query_api`

## Tool Schema

Add a third OpenAI-compatible function tool:

- `query_api(method, path, body?)`

Schema details:

- `method`: HTTP method such as `GET` or `POST`
- `path`: API path such as `/items/`
- `body`: optional JSON string for request bodies

## Authentication and Configuration

The agent must keep all configuration in environment variables.

Plan:

1. Continue loading `.env.agent.secret` for:
   - `LLM_API_KEY`
   - `LLM_API_BASE`
   - `LLM_MODEL`
2. Also load `.env.docker.secret` for:
   - `LMS_API_KEY`
3. Read `AGENT_API_BASE_URL` from the environment, defaulting to
   `http://localhost:42002`.
4. Send the backend API key as:
   - `Authorization: Bearer <LMS_API_KEY>`

## Agent Changes

Keep the Task 2 loop and add one more tool executor.

Implementation plan:

1. Add the `query_api` schema to the tools list.
2. Implement a helper that makes authenticated HTTP requests to the backend.
3. Return a JSON string from the tool with:
   - `status_code`
   - `body`
4. Update the system prompt so the model knows:
   - use wiki tools for documentation questions
   - use `read_file` for source-code questions
   - use `query_api` for current data, status codes, and runtime errors
   - `source` is optional for API-driven answers

## Testing Plan

Add two more regression tests:

1. A source-code question about the backend framework that should use
   `read_file`.
2. A live-data question about item count that should use `query_api`.

The tests will keep using a fake LLM server. For the API tool test, add a fake
backend server and verify that the request includes the `Authorization` header.

## Benchmark Plan

Run `uv run run_eval.py` once after implementing `query_api`.

Initial benchmark diagnosis:

- First attempt result: `0/10`
- First failure:
  - question 0 failed before tool execution because the configured OpenRouter
    free model returned `429` temporary upstream rate limiting
- Observed environment status:
  - local backend is running and reachable with the LMS API key
  - the current blocker is LLM availability, not `query_api`
- Main risks confirmed by the first run:
  - free LLM provider may return `429` rate-limit errors
  - prompt/tool selection still needs evaluation once the provider responds

Iteration strategy:

1. Run the benchmark once and note the first failure.
2. Fix one failure class at a time:
   - tool choice
   - API request/auth
   - answer phrasing/source
3. Re-run and repeat until the local benchmark passes.
