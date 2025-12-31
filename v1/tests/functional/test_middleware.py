#!/usr/bin/env python3
"""
Functional tests for MCP server middleware.

Tests middleware behavior against a running MCP server via stdio transport.
These tests verify that middleware components work correctly end-to-end.

Usage:
    # Run with pytest
    pytest tests/functional/test_middleware.py -v

    # Or run directly
    python tests/functional/test_middleware.py
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio


# Get project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
SERVER_CONFIG_DIR = PROJECT_ROOT / "tests" / "server-configs" / "stdio"


class MCPStdioTestClient:
    """Simple MCP client for testing via stdio transport."""

    def __init__(self, server_cmd: list[str]):
        self.server_cmd = server_cmd
        self.process: subprocess.Popen | None = None
        self.request_id = 0

    def _next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    async def start(self):
        """Start the MCP server process."""
        self.process = subprocess.Popen(
            self.server_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    async def stop(self):
        """Stop the MCP server process."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    async def send_request(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC request and return the response."""
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise RuntimeError("Server process not started")

        request_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            request["params"] = params

        request_str = json.dumps(request) + "\n"
        self.process.stdin.write(request_str)
        self.process.stdin.flush()

        # Read responses, skipping notifications until we get our response
        max_reads = 50  # Safety limit
        for _ in range(max_reads):
            response_str = self.process.stdout.readline()
            if not response_str:
                stderr = self.process.stderr.read(1000) if self.process.stderr else ""
                raise RuntimeError(f"No response from server. stderr: {stderr}")

            response = json.loads(response_str)

            # Skip notifications (they have 'method' but no 'id')
            if "method" in response and "id" not in response:
                continue

            # Check if this is our response
            if response.get("id") == request_id:
                return response

        raise RuntimeError(f"Did not receive response for request {request_id}")

    async def initialize(self) -> dict:
        """Send initialize request."""
        return await self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "functional-test-client",
                "version": "1.0.0"
            }
        })

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Call a tool with arguments."""
        return await self.send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })


def get_server_command() -> list[str]:
    """Get the command to start the MCP server."""
    # Use the venv python interpreter
    venv_python = PROJECT_ROOT / "venv" / "bin" / "python"
    if not venv_python.exists():
        # Fall back to system python
        venv_python = sys.executable

    main_py = PROJECT_ROOT / "app" / "main.py"

    return [
        str(venv_python),
        str(main_py),
        "--config-dir",
        str(SERVER_CONFIG_DIR),
    ]


class TestToolCallPreprocessorMiddleware:
    """
    Tests for ToolCallPreprocessor middleware.

    The middleware filters out extra parameters that are not defined in the
    tool's JSON Schema. This handles non-standard MCP clients (like n8n)
    that add extra fields such as 'toolCallId'.
    """

    @pytest_asyncio.fixture
    async def mcp_client(self):
        """Create and start an MCP client for testing."""
        client = MCPStdioTestClient(get_server_command())
        await client.start()
        await client.initialize()
        yield client
        await client.stop()

    @pytest.mark.asyncio
    async def test_tool_call_with_extra_parameter_filtered(self, mcp_client):
        """
        Test that extra parameters (like n8n's toolCallId) are filtered.

        Without the middleware, Pydantic would reject the request with:
        "Extra inputs are not permitted"

        With the middleware, the extra field is filtered out and the
        tool executes successfully.
        """
        # Call execute_kubectl with an extra 'toolCallId' parameter
        # This simulates what n8n sends
        response = await mcp_client.call_tool(
            "execute_kubectl",
            {
                "command": "kubectl version --client",
                "toolCallId": "call_abc123xyz",  # Extra param from n8n
            }
        )

        # Should NOT have a JSON-RPC error (validation error)
        assert "error" not in response, (
            f"Tool call failed with error: {response.get('error')}. "
            "The middleware should filter extra parameters."
        )

        # Should have a result
        assert "result" in response
        result = response["result"]

        # The tool should execute (isError may be true if kubectl not installed,
        # but the important thing is it didn't fail validation)
        assert "content" in result, "Response should have content"

    @pytest.mark.asyncio
    async def test_tool_call_with_multiple_extra_parameters(self, mcp_client):
        """
        Test that multiple extra parameters are all filtered.

        Some clients might add several non-standard fields.
        """
        response = await mcp_client.call_tool(
            "execute_kubectl",
            {
                "command": "kubectl version --client",
                "toolCallId": "call_abc123",
                "requestId": "req_xyz789",
                "timestamp": "2024-01-01T00:00:00Z",
                "_internal": {"some": "data"},
            }
        )

        # Should NOT have a JSON-RPC error
        assert "error" not in response, (
            f"Tool call failed: {response.get('error')}. "
            "Middleware should filter all extra parameters."
        )

        # Should have a result
        assert "result" in response

    @pytest.mark.asyncio
    async def test_tool_call_with_only_valid_parameters(self, mcp_client):
        """
        Test that valid parameters pass through unchanged.

        When all parameters are valid (in schema), nothing should be filtered.
        """
        response = await mcp_client.call_tool(
            "execute_kubectl",
            {
                "command": "kubectl version --client",
                # timeout is a valid parameter for execute_kubectl
            }
        )

        assert "error" not in response
        assert "result" in response

    @pytest.mark.asyncio
    async def test_tool_call_with_valid_optional_parameter(self, mcp_client):
        """
        Test that valid optional parameters are preserved.
        """
        response = await mcp_client.call_tool(
            "execute_kubectl",
            {
                "command": "kubectl version --client",
                "timeout": 30,  # Valid optional parameter
                "toolCallId": "should_be_filtered",  # Invalid, should be filtered
            }
        )

        assert "error" not in response
        assert "result" in response

    @pytest.mark.asyncio
    async def test_describe_tool_with_extra_parameter(self, mcp_client):
        """
        Test that describe_* tools also handle extra parameters.
        """
        response = await mcp_client.call_tool(
            "describe_kubectl",
            {
                "command": None,
                "toolCallId": "call_describe_123",
            }
        )

        assert "error" not in response, (
            f"Describe tool failed: {response.get('error')}"
        )
        assert "result" in response


# Allow running directly for quick testing
async def main():
    """Run tests directly without pytest."""
    print("Running ToolCallPreprocessor middleware functional tests...")
    print(f"Server config: {SERVER_CONFIG_DIR}")
    print("-" * 60)

    client = MCPStdioTestClient(get_server_command())

    try:
        print("Starting MCP server...")
        await client.start()

        print("Initializing connection...")
        init_response = await client.initialize()
        print(f"Initialized: {init_response.get('result', {}).get('serverInfo', {})}")

        # Test 1: Extra parameter filtered
        print("\nTest 1: Tool call with extra 'toolCallId' parameter...")
        response = await client.call_tool(
            "execute_kubectl",
            {
                "command": "kubectl version --client",
                "toolCallId": "call_abc123xyz",
            }
        )

        if "error" in response:
            print(f"  FAILED: {response['error']}")
        else:
            print("  PASSED: Extra parameter was filtered, tool executed")
            result = response.get("result", {})
            is_error = result.get("isError", False)
            print(f"  Tool result isError: {is_error}")

        # Test 2: Multiple extra parameters
        print("\nTest 2: Tool call with multiple extra parameters...")
        response = await client.call_tool(
            "execute_kubectl",
            {
                "command": "kubectl version --client",
                "toolCallId": "call_123",
                "requestId": "req_456",
                "extra": "field",
            }
        )

        if "error" in response:
            print(f"  FAILED: {response['error']}")
        else:
            print("  PASSED: All extra parameters were filtered")

        print("\n" + "=" * 60)
        print("Functional tests completed!")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
