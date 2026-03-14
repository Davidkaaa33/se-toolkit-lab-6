#!/usr/bin/env python3
"""Documentation agent with two local file tools."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx


ENV_FILE = Path(".env.agent.secret")
PROJECT_ROOT = Path(__file__).resolve().parent
MAX_TOOL_CALLS = 10
SYSTEM_PROMPT = """You answer questions using this repository's wiki.
Use list_files to discover wiki files, then use read_file to inspect them.
When you know the answer, respond with JSON:
{"answer":"...","source":"wiki/file.md#section-anchor"}
Always include a source reference from the wiki when possible."""
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from the project root.",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a project path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from the project root.",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
]


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE pairs into the environment if missing."""
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def require_env(name: str) -> str:
    """Return a required environment variable or exit with an error."""
    value = os.environ.get(name, "").strip()
    if value:
        return value

    print(f"Missing required environment variable: {name}", file=sys.stderr)
    raise SystemExit(1)


def resolve_repo_path(raw_path: str) -> Path:
    """Resolve a user path and ensure it stays within the repository."""
    candidate = (PROJECT_ROOT / raw_path).resolve()
    try:
        candidate.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError("Access denied: path must stay inside the project directory") from exc
    return candidate


def read_file(path: str) -> str:
    """Read a project file with repo-root path protection."""
    try:
        resolved = resolve_repo_path(path)
    except ValueError as exc:
        return str(exc)

    if not resolved.exists():
        return f"Error: file does not exist: {path}"
    if not resolved.is_file():
        return f"Error: path is not a file: {path}"

    return resolved.read_text()


def list_files(path: str) -> str:
    """List directory entries with repo-root path protection."""
    try:
        resolved = resolve_repo_path(path)
    except ValueError as exc:
        return str(exc)

    if not resolved.exists():
        return f"Error: directory does not exist: {path}"
    if not resolved.is_dir():
        return f"Error: path is not a directory: {path}"

    entries = sorted(item.name for item in resolved.iterdir())
    return "\n".join(entries)


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Dispatch a supported tool call."""
    path = arguments.get("path", "")
    if not isinstance(path, str):
        return "Error: path must be a string"

    if name == "read_file":
        return read_file(path)
    if name == "list_files":
        return list_files(path)
    return f"Error: unknown tool: {name}"


def extract_text_content(message: dict[str, Any]) -> str:
    """Extract assistant text from an OpenAI-compatible message."""
    content = message.get("content", "")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if isinstance(text, str):
                    text_parts.append(text)
        return "".join(text_parts).strip()

    return ""


def parse_final_answer(text: str) -> tuple[str, str]:
    """Parse the assistant's final JSON answer or fall back to plain text."""
    if text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text, ""

        if isinstance(payload, dict):
            answer = payload.get("answer", "")
            source = payload.get("source", "")
            if isinstance(answer, str) and isinstance(source, str):
                return answer, source

    return "", ""


def ask_llm(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Send a chat completions request and return the assistant message."""
    api_key = require_env("LLM_API_KEY")
    api_base = require_env("LLM_API_BASE").rstrip("/")
    model = require_env("LLM_MODEL")

    request_body = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
    }

    with httpx.Client(timeout=55.0) as client:
        response = client.post(
            f"{api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        print(f"LLM API returned {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        raise SystemExit(1) from exc

    payload = response.json()
    choices = payload.get("choices", [])
    if not choices:
        print("LLM response did not contain choices", file=sys.stderr)
        raise SystemExit(1)

    message = choices[0].get("message", {})
    if not isinstance(message, dict):
        print("LLM response did not contain a message", file=sys.stderr)
        raise SystemExit(1)

    return message


def run_agent(question: str) -> dict[str, Any]:
    """Run the agentic loop until the model returns a final answer."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tool_history: list[dict[str, Any]] = []
    last_answer = ""
    last_source = ""

    for _ in range(MAX_TOOL_CALLS + 1):
        message = ask_llm(messages)
        tool_calls = message.get("tool_calls", [])

        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": message.get("content", ""),
        }
        if tool_calls:
            assistant_message["tool_calls"] = tool_calls
        messages.append(assistant_message)

        if not tool_calls:
            final_text = extract_text_content(message)
            answer, source = parse_final_answer(final_text)
            if answer:
                last_answer = answer
            if source:
                last_source = source
            break

        if len(tool_history) >= MAX_TOOL_CALLS:
            break

        for tool_call in tool_calls:
            if len(tool_history) >= MAX_TOOL_CALLS:
                break

            tool_id = tool_call.get("id", "")
            function = tool_call.get("function", {})
            name = function.get("name", "")
            arguments_text = function.get("arguments", "{}")

            try:
                arguments = json.loads(arguments_text)
            except json.JSONDecodeError:
                arguments = {}

            result = execute_tool(name, arguments)
            tool_history.append({"tool": name, "args": arguments, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": result,
                }
            )

    if not last_answer:
        last_answer = "I could not produce a final answer within the tool-call limit."

    return {
        "answer": last_answer,
        "source": last_source,
        "tool_calls": tool_history,
    }


def main() -> int:
    """Run the CLI agent."""
    if len(sys.argv) < 2:
        print('Usage: uv run agent.py "Your question"', file=sys.stderr)
        return 1

    question = sys.argv[1].strip()
    if not question:
        print("Question must not be empty", file=sys.stderr)
        return 1

    load_env_file(ENV_FILE)
    output = run_agent(question)
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
