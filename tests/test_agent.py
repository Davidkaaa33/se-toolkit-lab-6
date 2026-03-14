"""Regression tests for agent.py.

These tests run agent.py as a subprocess and verify:
- Exit code is 0
- stdout contains valid JSON
- JSON has required fields: answer and tool_calls
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


AGENT_PATH = Path(__file__).parent.parent / "agent.py"


def run_agent(question: str) -> tuple[int, str, str]:
    """Run agent.py with a question.

    Args:
        question: The question to pass to the agent.

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    result = subprocess.run(
        [sys.executable, str(AGENT_PATH), question],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode, result.stdout, result.stderr


class TestAgentOutput:
    """Test suite for agent.py output validation."""

    def test_agent_returns_valid_json_with_required_fields(self):
        """Test that agent outputs valid JSON with 'answer' and 'tool_calls' fields."""
        question = "What is the capital of France?"

        returncode, stdout, stderr = run_agent(question)

        # Check exit code
        assert returncode == 0, f"Agent exited with code {returncode}, stderr: {stderr}"

        # Check stdout is not empty
        assert stdout.strip(), "Agent produced no output"

        # Check stdout is valid JSON
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            pytest.fail(f"Agent output is not valid JSON: {stdout[:200]}. Error: {e}")

        # Check required fields exist
        assert "answer" in data, f"Missing 'answer' field in output: {stdout[:200]}"
        assert "tool_calls" in data, (
            f"Missing 'tool_calls' field in output: {stdout[:200]}"
        )

        # Check field types
        assert isinstance(data["answer"], str), (
            f"'answer' should be a string, got {type(data['answer'])}"
        )
        assert isinstance(data["tool_calls"], list), (
            f"'tool_calls' should be an array, got {type(data['tool_calls'])}"
        )

        # Check answer is not empty
        assert len(data["answer"].strip()) > 0, "'answer' field is empty"


class TestDocumentationAgent:
    """Test suite for documentation agent with tool calling."""

    def test_agent_uses_read_file_for_merge_conflict_question(self):
        """Test that agent uses read_file tool when asked about merge conflicts."""
        question = "How do you resolve a merge conflict?"

        returncode, stdout, stderr = run_agent(question)

        # Check exit code
        assert returncode == 0, f"Agent exited with code {returncode}, stderr: {stderr}"

        # Check stdout is valid JSON
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            pytest.fail(f"Agent output is not valid JSON: {stdout[:200]}. Error: {e}")

        # Check required fields exist
        assert "answer" in data, f"Missing 'answer' field in output: {stdout[:200]}"
        assert "tool_calls" in data, (
            f"Missing 'tool_calls' field in output: {stdout[:200]}"
        )

        # Check that read_file was used
        tool_names = [tc.get("tool", "") for tc in data["tool_calls"]]
        assert "read_file" in tool_names, (
            f"Expected 'read_file' in tool calls, got: {tool_names}"
        )

        # Check that source or answer references a wiki file about merge conflicts
        source = data.get("source", "")
        answer = data.get("answer", "")
        combined = f"{source} {answer}".lower()
        assert "merge" in combined and "conflict" in combined, (
            f"Expected 'merge conflict' in source or answer, got: source='{source}', answer='{answer[:100]}'"
        )

    def test_agent_uses_list_files_for_wiki_exploration_question(self):
        """Test that agent uses list_files tool when asked about wiki contents."""
        question = "What files are in the wiki?"

        returncode, stdout, stderr = run_agent(question)

        # Check exit code
        assert returncode == 0, f"Agent exited with code {returncode}, stderr: {stderr}"

        # Check stdout is valid JSON
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            pytest.fail(f"Agent output is not valid JSON: {stdout[:200]}. Error: {e}")

        # Check required fields exist
        assert "answer" in data, f"Missing 'answer' field in output: {stdout[:200]}"
        assert "tool_calls" in data, (
            f"Missing 'tool_calls' field in output: {stdout[:200]}"
        )

        # Check that list_files was used
        tool_names = [tc.get("tool", "") for tc in data["tool_calls"]]
        assert "list_files" in tool_names, (
            f"Expected 'list_files' in tool calls, got: {tool_names}"
        )


class TestSystemAgent:
    """Test suite for system agent with query_api tool."""

    def test_agent_uses_read_file_for_framework_question(self):
        """Test that agent uses read_file tool when asked about the backend framework."""
        question = "What framework does the backend use?"

        returncode, stdout, stderr = run_agent(question)

        # Check exit code
        assert returncode == 0, f"Agent exited with code {returncode}, stderr: {stderr}"

        # Check stdout is valid JSON
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            pytest.fail(f"Agent output is not valid JSON: {stdout[:200]}. Error: {e}")

        # Check required fields exist
        assert "answer" in data, f"Missing 'answer' field in output: {stdout[:200]}"
        assert "tool_calls" in data, (
            f"Missing 'tool_calls' field in output: {stdout[:200]}"
        )

        # Check that read_file was used
        tool_names = [tc.get("tool", "") for tc in data["tool_calls"]]
        assert "read_file" in tool_names, (
            f"Expected 'read_file' in tool calls, got: {tool_names}"
        )

        # Check that answer mentions FastAPI
        answer = data.get("answer", "").lower()
        assert "fastapi" in answer, f"Expected 'FastAPI' in answer, got: {answer[:200]}"

    def test_agent_uses_query_api_for_database_question(self):
        """Test that agent uses query_api tool when asked about database contents."""
        question = "How many items are in the database?"

        returncode, stdout, stderr = run_agent(question)

        # Check exit code
        assert returncode == 0, f"Agent exited with code {returncode}, stderr: {stderr}"

        # Check stdout is valid JSON
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            pytest.fail(f"Agent output is not valid JSON: {stdout[:200]}. Error: {e}")

        # Check required fields exist
        assert "answer" in data, f"Missing 'answer' field in output: {stdout[:200]}"
        assert "tool_calls" in data, (
            f"Missing 'tool_calls' field in output: {stdout[:200]}"
        )

        # Check that query_api was used
        tool_names = [tc.get("tool", "") for tc in data["tool_calls"]]
        assert "query_api" in tool_names, (
            f"Expected 'query_api' in tool calls, got: {tool_names}"
        )

        # Check that answer contains a number
        import re

        answer = data.get("answer", "")
        numbers = re.findall(r"\d+", answer)
        assert len(numbers) > 0, f"Expected a number in answer, got: {answer[:200]}"
