"""Regression test for the Task 1 CLI agent."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _FakeLLMHandler(BaseHTTPRequestHandler):
    """Serve a minimal OpenAI-compatible chat completions response."""

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/chat/completions":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        payload = json.loads(raw_body.decode("utf-8"))

        assert payload["messages"][1]["content"] == "What does REST stand for?"

        response = {
            "choices": [
                {
                    "message": {
                        "content": "Representational State Transfer."
                    }
                }
            ]
        }
        response_bytes = json.dumps(response).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        """Silence test server logging."""


def test_agent_outputs_answer_and_tool_calls() -> None:
    """Run agent.py as a subprocess and verify its stdout JSON contract."""
    repo_root = Path(__file__).resolve().parents[3]
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeLLMHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        "LLM_API_KEY": "test-key",
        "LLM_API_BASE": f"http://127.0.0.1:{server.server_port}",
        "LLM_MODEL": "chatgpt-test",
    }

    try:
        result = subprocess.run(
            [sys.executable, "agent.py", "What does REST stand for?"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "answer" in data
    assert "tool_calls" in data
    assert data["answer"] == "Representational State Transfer."
    assert data["tool_calls"] == []
