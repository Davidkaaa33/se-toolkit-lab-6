#!/usr/bin/env python3
"""Minimal Task 1 agent CLI."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx


ENV_FILE = Path(".env.agent.secret")
SYSTEM_PROMPT = "You are a concise assistant. Answer the user's question directly."


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


def extract_answer(payload: dict) -> str:
    """Extract assistant text from an OpenAI-compatible response."""
    choices = payload.get("choices", [])
    if not choices:
        print("LLM response did not contain choices", file=sys.stderr)
        raise SystemExit(1)

    message = choices[0].get("message", {})
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
        answer = "".join(text_parts).strip()
        if answer:
            return answer

    print("LLM response did not contain text content", file=sys.stderr)
    raise SystemExit(1)


def ask_llm(question: str) -> str:
    """Send the user question to the configured chat completions endpoint."""
    api_key = require_env("LLM_API_KEY")
    api_base = require_env("LLM_API_BASE").rstrip("/")
    model = require_env("LLM_MODEL")

    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
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

    return extract_answer(response.json())


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
    answer = ask_llm(question)
    output = {"answer": answer, "tool_calls": []}
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
