"""Regression tests for the CLI system agent."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _FakeLLMHandler(BaseHTTPRequestHandler):
    """Serve scripted OpenAI-compatible chat completions responses."""

    scenario = ""
    call_count = 0

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/chat/completions":
            self.send_error(404)
            return

        type(self).call_count += 1

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        payload = json.loads(raw_body.decode("utf-8"))

        if self.scenario == "plain":
            response = self._plain_response(payload)
        elif self.scenario == "read_file":
            response = self._read_file_response(payload)
        elif self.scenario == "list_files":
            response = self._list_files_response(payload)
        elif self.scenario == "framework":
            response = self._framework_response(payload)
        else:
            response = self._query_api_response(payload)

        response_bytes = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def _plain_response(self, payload: dict) -> dict:
        assert payload["messages"][1]["content"] == "What does REST stand for?"
        return {"choices": [{"message": {"content": "Representational State Transfer."}}]}

    def _read_file_response(self, payload: dict) -> dict:
        if self.call_count == 1:
            assert payload["messages"][1]["content"] == "How do you push commits?"
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_read",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": json.dumps({"path": "wiki/git-workflow.md"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }

        tool_message = payload["messages"][-1]
        assert tool_message["role"] == "tool"
        assert "## Push commits" in tool_message["content"]
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": "Publish the branch if needed, then push more commits to the published branch.",
                                "source": "wiki/git-workflow.md#push-commits",
                            }
                        )
                    }
                }
            ]
        }

    def _list_files_response(self, payload: dict) -> dict:
        if self.call_count == 1:
            assert payload["messages"][1]["content"] == "What files are in the wiki?"
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_list",
                                    "type": "function",
                                    "function": {
                                        "name": "list_files",
                                        "arguments": json.dumps({"path": "wiki"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }

        tool_message = payload["messages"][-1]
        assert tool_message["role"] == "tool"
        assert "git-workflow.md" in tool_message["content"]
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": "The wiki includes files such as git-workflow.md, github.md, docker.md, and many others.",
                                "source": "wiki/git-workflow.md#git-workflow-for-tasks",
                            }
                        )
                    }
                }
            ]
        }

    def _framework_response(self, payload: dict) -> dict:
        if self.call_count == 1:
            assert payload["messages"][1]["content"] == "What framework does the backend use?"
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_framework",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": json.dumps({"path": "backend/app/main.py"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }

        tool_message = payload["messages"][-1]
        assert "FastAPI" in tool_message["content"]
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": "The backend uses FastAPI.",
                                "source": "backend/app/main.py",
                            }
                        )
                    }
                }
            ]
        }

    def _query_api_response(self, payload: dict) -> dict:
        if self.call_count == 1:
            assert payload["messages"][1]["content"] == "How many items are in the database?"
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_api",
                                    "type": "function",
                                    "function": {
                                        "name": "query_api",
                                        "arguments": json.dumps(
                                            {"method": "GET", "path": "/items/"}
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }

        tool_message = payload["messages"][-1]
        parsed = json.loads(tool_message["content"])
        assert parsed["status_code"] == 200
        assert isinstance(parsed["body"], list)
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": "There are 2 items in the database.",
                                "source": "",
                            }
                        )
                    }
                }
            ]
        }

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        """Silence test server logging."""


class _FakeAPIHandler(BaseHTTPRequestHandler):
    """Serve a tiny protected backend response."""

    expected_api_key = ""

    def do_GET(self) -> None:  # noqa: N802
        assert self.headers.get("Authorization") == f"Bearer {self.expected_api_key}"
        assert self.path == "/items/"

        response = [
            {"id": 1, "type": "lab", "title": "Lab 06"},
            {"id": 2, "type": "task", "title": "Task 01"},
        ]
        response_bytes = json.dumps(response).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        """Silence test server logging."""


def _run_agent(question: str, scenario: str, *, with_api: bool = False) -> dict:
    repo_root = Path(__file__).resolve().parents[1]
    _FakeLLMHandler.scenario = scenario
    _FakeLLMHandler.call_count = 0

    llm_server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeLLMHandler)
    llm_thread = threading.Thread(target=llm_server.serve_forever, daemon=True)
    llm_thread.start()

    api_server = None
    api_thread = None
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        "LLM_API_KEY": "test-key",
        "LLM_API_BASE": f"http://127.0.0.1:{llm_server.server_port}",
        "LLM_MODEL": "test-model",
        "LMS_API_KEY": "test-lms-key",
    }

    if with_api:
        _FakeAPIHandler.expected_api_key = env["LMS_API_KEY"]
        api_server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeAPIHandler)
        api_thread = threading.Thread(target=api_server.serve_forever, daemon=True)
        api_thread.start()
        env["AGENT_API_BASE_URL"] = f"http://127.0.0.1:{api_server.server_port}"

    try:
        result = subprocess.run(
            [sys.executable, "agent.py", question],
            cwd=repo_root,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
            check=False,
        )
    finally:
        llm_server.shutdown()
        llm_server.server_close()
        llm_thread.join(timeout=2)
        if api_server is not None and api_thread is not None:
            api_server.shutdown()
            api_server.server_close()
            api_thread.join(timeout=2)

    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_agent_outputs_answer_and_tool_calls() -> None:
    data = _run_agent("What does REST stand for?", "plain")
    assert data["answer"] == "Representational State Transfer."
    assert data["tool_calls"] == []
    assert data["source"] == ""


def test_agent_uses_read_file_and_returns_source() -> None:
    data = _run_agent("How do you push commits?", "read_file")
    assert data["source"] == "wiki/git-workflow.md#push-commits"
    assert data["tool_calls"][0]["tool"] == "read_file"
    assert data["tool_calls"][0]["args"] == {"path": "wiki/git-workflow.md"}


def test_agent_uses_list_files_for_wiki_listing() -> None:
    data = _run_agent("What files are in the wiki?", "list_files")
    assert data["tool_calls"][0]["tool"] == "list_files"
    assert data["tool_calls"][0]["args"] == {"path": "wiki"}
    assert "git-workflow.md" in data["tool_calls"][0]["result"]


def test_agent_reads_source_code_for_framework_question() -> None:
    data = _run_agent("What framework does the backend use?", "framework")
    assert data["answer"] == "The backend uses FastAPI."
    assert data["tool_calls"][0]["tool"] == "read_file"
    assert data["tool_calls"][0]["args"] == {"path": "backend/app/main.py"}


def test_agent_uses_query_api_for_live_item_count() -> None:
    data = _run_agent("How many items are in the database?", "query_api", with_api=True)
    assert data["answer"] == "There are currently 2 items stored in the database."
    assert data["tool_calls"][0]["tool"] == "query_api"
    assert data["tool_calls"][0]["args"] == {"method": "GET", "path": "/items/"}
    parsed = json.loads(data["tool_calls"][0]["result"])
    assert parsed["status_code"] == 200
    assert len(parsed["body"]) == 2
