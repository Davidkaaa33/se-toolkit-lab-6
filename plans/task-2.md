# Task 2 Plan

## Goal

Upgrade `agent.py` from a simple CLI into a documentation agent that can:

1. ask the LLM for tool calls
2. execute `read_file` and `list_files`
3. feed tool results back into the conversation
4. return JSON with `answer`, `source`, and `tool_calls`

## Tool Schemas

Define two OpenAI-compatible function tools:

- `read_file(path)`
- `list_files(path)`

Each tool schema will describe a single required string parameter named `path`.

## Agentic Loop

Keep the loop simple:

1. Start with a system prompt and the user question.
2. Send messages and tool schemas to the LLM.
3. If the response contains tool calls, execute them and append their results as `tool` messages.
4. If the response contains a final assistant message without tool calls, extract `answer` and `source` and return JSON.
5. Stop after at most 10 tool calls.

If the loop reaches the limit before a clean final answer, return the best answer available so far and include the collected tool calls.

## Path Security

Both tools must reject paths outside the project directory.

Plan:

1. Resolve the requested path against the project root.
2. Normalize it with `Path.resolve()`.
3. Check that the resolved path stays inside the project root.
4. Return an error string instead of reading/listing anything outside the repo.

This blocks `../` traversal and absolute paths that escape the repository.

## Tool Results

- `read_file` returns the file text or an error message.
- `list_files` returns a newline-separated directory listing or an error message.
- Every executed tool call is recorded in the output `tool_calls` array with:
  - `tool`
  - `args`
  - `result`

## System Prompt Strategy

Use a short system prompt that tells the model:

- answer using the project wiki
- use `list_files` first when it needs to discover files
- use `read_file` to inspect wiki documents
- include a `source` reference in the form `path#section-anchor`

## Testing Plan

Keep the same subprocess strategy as Task 1, but make the fake LLM return scripted tool-calling responses.

Add two regression tests:

1. A merge-conflict question that triggers `read_file` and expects a `wiki/git-workflow.md...` source.
2. A wiki-listing question that triggers `list_files`.

The fake test server will:

1. return a tool call on the first request
2. inspect the tool result in the next request
3. return the final answer with a source reference

## Documentation Plan

Update `AGENT.md` to document:

- the two tools
- the loop behavior
- path security
- the `source` field
- the system prompt strategy
