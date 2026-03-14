#!/usr/bin/env python3
"""System agent with wiki, source, and API tools."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx


ENV_FILES = [Path(".env.agent.secret"), Path(".env.docker.secret")]
PROJECT_ROOT = Path(__file__).resolve().parent
MAX_TOOL_CALLS = 10
DEFAULT_AGENT_API_BASE_URL = "http://localhost:42002"
SYSTEM_PROMPT = """You answer questions about this repository and its running system.
Use list_files to discover directories, use read_file to inspect wiki or source files,
and use query_api for live backend data, auth behavior, and runtime errors.
Use read_file for source-code questions such as framework, ports, Docker, and bug diagnosis.
Use query_api for current counts, status codes, or endpoint failures.
Respond with JSON:
{"answer":"...","source":"optional-file-reference-or-empty-string"}
If the answer comes from live API data, source may be an empty string."""
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
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Call the deployed backend API for live data, status codes, or runtime errors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method such as GET or POST.",
                    },
                    "path": {
                        "type": "string",
                        "description": "API path such as /items/ or /analytics/completion-rate?lab=lab-99.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional JSON request body as a string.",
                    },
                },
                "required": ["method", "path"],
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


def load_all_env_files() -> None:
    """Load local convenience env files without overriding real environment values."""
    for path in ENV_FILES:
        load_env_file(path)


def require_env(name: str) -> str:
    """Return a required environment variable or exit with an error."""
    value = os.environ.get(name, "").strip()
    if value:
        return value

    print(f"Missing required environment variable: {name}", file=sys.stderr)
    raise SystemExit(1)


def get_agent_api_base_url() -> str:
    """Return the backend base URL from the environment or the default."""
    return os.environ.get("AGENT_API_BASE_URL", DEFAULT_AGENT_API_BASE_URL).rstrip("/")


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


def query_api(method: str, path: str, body: str | None = None) -> str:
    """Call the backend API with the LMS API key and return a JSON string."""
    if not isinstance(method, str) or not method.strip():
        return json.dumps({"error": "method must be a non-empty string"})
    if not isinstance(path, str) or not path.startswith("/"):
        return json.dumps({"error": "path must start with /"})

    api_key = require_env("LMS_API_KEY")
    base_url = get_agent_api_base_url()
    request_kwargs: dict[str, Any] = {
        "method": method.upper(),
        "url": f"{base_url}{path}",
        "headers": {"Authorization": f"Bearer {api_key}"},
    }

    if body:
        try:
            request_kwargs["json"] = json.loads(body)
        except json.JSONDecodeError:
            request_kwargs["content"] = body
            request_kwargs["headers"]["Content-Type"] = "application/json"

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.request(**request_kwargs)
    except httpx.HTTPError as exc:
        return json.dumps({"error": str(exc)})

    try:
        payload_body: Any = response.json()
    except ValueError:
        payload_body = response.text

    return json.dumps({"status_code": response.status_code, "body": payload_body})


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Dispatch a supported tool call."""
    if name == "read_file":
        path = arguments.get("path", "")
        if not isinstance(path, str):
            return "Error: path must be a string"
        return read_file(path)

    if name == "list_files":
        path = arguments.get("path", "")
        if not isinstance(path, str):
            return "Error: path must be a string"
        return list_files(path)

    if name == "query_api":
        method = arguments.get("method", "")
        path = arguments.get("path", "")
        body = arguments.get("body")
        if not isinstance(method, str):
            return json.dumps({"error": "method must be a string"})
        if not isinstance(path, str):
            return json.dumps({"error": "path must be a string"})
        if body is not None and not isinstance(body, str):
            return json.dumps({"error": "body must be a string when provided"})
        return query_api(method, path, body)

    return f"Error: unknown tool: {name}"


def extract_text_content(message: dict[str, Any]) -> str:
    """Extract assistant text from an OpenAI-compatible message."""
    content = message.get("content") or ""

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
            "content": message.get("content") or "",
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

    load_all_env_files()
    output = run_agent(question)
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
