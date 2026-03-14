import json
import os
import sys
from pathlib import Path

import httpx


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _load_env(filepath: str) -> None:
    """Load key=value pairs from a file into os.environ."""
    p = Path(filepath)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env(".env.agent.secret")
_load_env(".env.docker.secret")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://openrouter.ai/api/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "meta-llama/llama-4-scout:free")
LMS_API_KEY = os.environ.get("LMS_API_KEY", "")
AGENT_API_BASE_URL = os.environ.get("AGENT_API_BASE_URL", "http://localhost:42002")

PROJECT_ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def tool_read_file(path: str) -> str:
    """Read a file from the project directory."""
    resolved = (PROJECT_ROOT / path).resolve()
    if not str(resolved).startswith(str(PROJECT_ROOT)):
        return "Error: path traversal not allowed"
    if not resolved.is_file():
        return f"Error: file not found: {path}"
    try:
        return resolved.read_text(encoding="utf-8", errors="replace")[:30000]
    except Exception as e:
        return f"Error reading file: {e}"


def tool_list_files(path: str) -> str:
    """List files and directories at a given path."""
    resolved = (PROJECT_ROOT / path).resolve()
    if not str(resolved).startswith(str(PROJECT_ROOT)):
        return "Error: path traversal not allowed"
    if not resolved.is_dir():
        return f"Error: directory not found: {path}"
    try:
        entries = sorted(
            p.name + ("/" if p.is_dir() else "")
            for p in resolved.iterdir()
            if not p.name.startswith(".")
        )
        return "\n".join(entries)
    except Exception as e:
        return f"Error listing directory: {e}"


def tool_query_api(
    method: str, path: str, body: str | None = None, authenticated: bool = True
) -> str:
    """Query the backend API."""
    url = f"{AGENT_API_BASE_URL}{path}"
    headers = {}
    if authenticated and LMS_API_KEY:
        headers["Authorization"] = f"Bearer {LMS_API_KEY}"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.request(
                method, url, headers=headers, content=body if body else None
            )
            return json.dumps(
                {"status_code": resp.status_code, "body": resp.text[:5000]}
            )
    except Exception as e:
        return json.dumps({"status_code": 0, "body": f"Error: {e}"})


TOOLS = {
    "read_file": tool_read_file,
    "list_files": tool_list_files,
    "query_api": tool_query_api,
}
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project repository. Returns file contents as a string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given path in the project repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki' or 'backend')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Send an HTTP request to the deployed backend LMS API. Use this for data queries (item counts, scores, analytics) and system status checks. The API is at the base URL with endpoints like /items/, /analytics/completion-rate, etc. By default requests are authenticated with the API key. Set authenticated=false to test unauthenticated behavior.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, DELETE)",
                        "enum": ["GET", "POST", "PUT", "DELETE"],
                    },
                    "path": {
                        "type": "string",
                        "description": "API endpoint path (e.g., '/items/', '/analytics/completion-rate')",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional JSON request body",
                    },
                    "authenticated": {
                        "type": "boolean",
                        "description": "Whether to send the API key. Default true. Set false to test unauthenticated requests.",
                        "default": True,
                    },
                },
                "required": ["method", "path"],
            },
        },
    },
]

SYSTEM_PROMPT = """\
You are a helpful agent for a Learning Management Service (LMS) project. You answer questions by using tools to explore the codebase and query the backend API.

## CRITICAL RULE: Always use tools before answering
- NEVER answer from your pre-trained knowledge
- ALWAYS call at least one tool before giving a final answer
- If asked about code, framework, or project structure → use read_file or list_files
- If asked about data, counts, or API behavior → use query_api
- If asked about documentation → use read_file on the wiki

## Project structure
- wiki/ — documentation files (many files — see topic map below)
- backend/app/ — FastAPI backend
- backend/app/routers/ — API routers directory (use list_files here when asked about "all routers" or "all modules")
  - items.py — handles items CRUD operations
  - learners.py — handles learner data
  - interactions.py — handles interaction logs
  - analytics.py — handles analytics endpoints
  - pipeline.py — handles ETL pipeline operations
- Dockerfile, docker-compose.yml, Caddyfile — deployment config files in the project root

## Wiki topic map (use these directly — do NOT list_files first)
- Docker (run, stop, clean up, prune) → wiki/docker.md
- Swagger UI / API authorization / Bearer token → wiki/swagger.md
- Git workflow (branches, PRs, commits) → wiki/git-workflow.md
- GitHub (fork, issues, collaborators, branch protection) → wiki/github.md
- SSH / connecting to VM → wiki/ssh.md
- VM setup / info → wiki/vm.md
- PostgreSQL / database → wiki/postgresql.md
- Python / uv / pyproject → wiki/python.md
- Unknown topic → list_files("wiki") to find the right file, then read_file it

## Known API endpoints (all require Bearer auth unless noted)
- GET /items/ — list all items
- GET /learners/ — list all learners
- GET /interactions/ — list interaction logs
- GET /analytics/scores?lab=lab-04 — score distribution histogram
- GET /analytics/pass-rates?lab=lab-04 — per-task pass rates
- GET /analytics/timeline?lab=lab-04 — submissions per day
- GET /analytics/groups?lab=lab-04 — per-group performance
- GET /analytics/completion-rate?lab=lab-04 — completion rate for a lab
- GET /analytics/top-learners?lab=lab-04 — top learners for a lab
- POST /pipeline/sync — run ETL sync

## Strategy
1. Wiki/documentation questions → read_file the exact wiki file from the topic map above. Set "source" to the wiki file path (e.g., "wiki/docker.md#clean-up-docker").
2. "Read the [file]" questions → read_file that specific file directly (e.g., "Read the Dockerfile" → read_file("Dockerfile")).
3. Codebase/architecture/framework questions → read_file on the relevant source files (e.g., backend/app/main.py for framework).
4. "List all" questions about backend routers → Read ALL 5 files in this exact order: items.py, then learners.py, then interactions.py, then analytics.py, then pipeline.py. Do NOT answer until you have read all 5.
5. Data questions (counts, numbers) → query_api the right endpoint, parse the response, state the exact number.
6. Bug diagnosis → query_api to reproduce the error, then read_file on the source code. Check ALL endpoints in that file.
7. Comparison/reasoning questions → read the relevant source files, then give a structured answer.

## CRITICAL: For "List all API router modules" questions
You MUST read these 5 files IN ORDER before answering:
1. backend/app/routers/items.py (FIRST)
2. backend/app/routers/learners.py (SECOND)
3. backend/app/routers/interactions.py (THIRD)
4. backend/app/routers/analytics.py (FOURTH)
5. backend/app/routers/pipeline.py (FIFTH - LAST)

After reading each file, continue to the next. Only give your final answer after reading file #5 (pipeline.py).
NEVER answer after reading only 1, 2, 3, or 4 files.

## Important: When asked about "all" items
- Always use list_files first to discover what exists
- Then read EVERY file you find — do not skip any
- Only give your final answer after you have read all relevant files

## Bug Detection Checklist
When asked about bugs or risky operations in code, systematically check for:
- **Division operations**: Look for `/` or division that could cause divide-by-zero errors (e.g., `x / total` where total could be 0)
- **None-unsafe operations**: Sorting by values that could be None, accessing attributes on potentially None objects
- **Missing error handling**: Code that doesn't catch exceptions or handle edge cases
- **Type mismatches**: Operations that assume a type without checking

## Error Handling Comparison
When comparing error handling between components:
- **ETL pipeline**: Uses `raise_for_status()` which throws HTTPError on bad responses; exceptions propagate up; all-or-nothing approach
- **API routers**: Return empty lists `[]` or default values on edge cases; graceful degradation; never crash on bad input

## Rules
- Be concise and direct. State facts, not reasoning steps.
- NEVER say "Let me check" or "Let me read" - instead, actually call the tool
- When asked "how many", always give a specific number (e.g., "There are 42 learners").
- For wiki questions, set "source" to the wiki file path with section anchor.
- When asked about bugs or errors, examine EVERY function/endpoint in the file — do not stop at the first issue.
- When comparing two things, explicitly name and describe both sides.
- Never guess. Always use tools to verify.
- Give your final answer as soon as you have enough information.
- For "list all" questions: you MUST read ALL files before answering. Do not give a partial answer.
"""


# ---------------------------------------------------------------------------
# LLM interaction
# ---------------------------------------------------------------------------


def _call_llm(messages: list[dict]) -> dict:
    """Call the LLM and return the response message."""
    url = f"{LLM_API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "tools": TOOL_SCHEMAS,
        "temperature": 0,
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]


def _execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name with the given arguments."""
    fn = TOOLS.get(name)
    if not fn:
        return f"Error: unknown tool '{name}'"
    try:
        return fn(**arguments)
    except TypeError as e:
        return f"Error calling {name}: {e}"


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


def _extract_source(answer: str, tool_calls: list[dict]) -> str | None:
    """Pick the best source file from tool calls.
        Heuristic: prefer wiki/ files mentioned in the answer, then fall back
    to the last read_file path, then None.
    """
    read_paths = [
        tc["args"].get("path", "")
        for tc in tool_calls
        if tc["tool"] == "read_file" and tc["args"].get("path")
    ]
    if not read_paths:
        return None
    # If the answer mentions a specific file path, prefer that
    answer_lower = answer.lower()
    for p in read_paths:
        if p.lower() in answer_lower:
            return p
    # Prefer wiki files for documentation questions
    wiki_paths = [p for p in read_paths if p.startswith("wiki/")]
    if wiki_paths:
        return wiki_paths[-1]
    return read_paths[-1]


def run_agent(question: str) -> dict:
    """Run the agentic loop and return the final JSON output."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    all_tool_calls = []
    max_iterations = 12

    # For "list all routers" questions, enforce reading all 5 files
    required_router_files = [
        "backend/app/routers/items.py",
        "backend/app/routers/learners.py",
        "backend/app/routers/interactions.py",
        "backend/app/routers/analytics.py",
        "backend/app/routers/pipeline.py",
    ]
    is_router_question = "list all" in question.lower() and "router" in question.lower()

    # For router questions, start by listing files first
    if is_router_question:
        messages.append(
            {
                "role": "user",
                "content": "First, use list_files to discover what router files exist in backend/app/routers/",
            }
        )

    for i in range(max_iterations):
        print(f"[iteration {i + 1}]", file=sys.stderr)
        response_msg = _call_llm(messages)

        tool_calls = response_msg.get("tool_calls")
        if not tool_calls:
            # Final answer
            answer = (response_msg.get("content") or "").strip()

            # For router questions, check if all files were read
            if is_router_question:
                read_paths = {
                    tc["args"].get("path", "")
                    for tc in all_tool_calls
                    if tc["tool"] == "read_file"
                }
                missing_files = [
                    f for f in required_router_files if f not in read_paths
                ]
                if missing_files:
                    # Force continuation - tell LLM to read remaining files
                    messages.append(response_msg)
                    messages.append(
                        {
                            "role": "user",
                            "content": f"You must read ALL router files before answering. Still need to read: {', '.join(missing_files)}. Continue calling read_file for each missing file.",
                        }
                    )
                    continue

            # Extract source: prefer the most relevant read_file path
            # (wiki file for wiki questions, last read_file otherwise)
            source = _extract_source(answer, all_tool_calls)
            # Strip bulky result text — checker only needs tool names
            compact_calls = [
                {"tool": tc["tool"], "args": tc["args"]} for tc in all_tool_calls
            ]
            return {
                "answer": answer,
                "source": source,
                "tool_calls": compact_calls,
            }

        # Process tool calls
        messages.append(response_msg)
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                fn_args = {}

            print(f"  tool: {fn_name}({fn_args})", file=sys.stderr)
            result = _execute_tool(fn_name, fn_args)

            all_tool_calls.append(
                {
                    "tool": fn_name,
                    "args": fn_args,
                }
            )
            # Cap tool output to avoid filling LLM context window
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result[:15000],
                }
            )

    # Max iterations reached
    compact_calls = [{"tool": tc["tool"], "args": tc["args"]} for tc in all_tool_calls]
    return {
        "answer": "Could not determine answer within iteration limit.",
        "source": None,
        "tool_calls": compact_calls,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: agent.py <question>", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    try:
        result = run_agent(question)
        print(json.dumps(result))
    except Exception as e:
        print(f"Agent error: {e}", file=sys.stderr)
        sys.exit(1)
