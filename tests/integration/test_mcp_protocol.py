#!/usr/bin/env python3
"""
MCP Protocol Compliance Tests.

Tests MCP protocol methods per the 2024-11-05 specification.
Verifies proper JSON-RPC responses for all core MCP operations.
"""

import json
from typing import Any

import httpx
import pytest


class MCPClient:
    """Simple MCP client for testing."""

    def __init__(self, client: httpx.Client):
        self.client = client
        self.request_id = 0
        self.session_id: str | None = None

    def send(self, method: str, params: dict | None = None) -> dict[str, Any]:
        """Send a JSON-RPC request and return the response."""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
        }
        if params:
            request["params"] = params

        headers = {"Accept": "application/json, text/event-stream"}
        if self.session_id:
            headers["mcp-session-id"] = self.session_id

        response = self.client.post("/mcp", json=request, headers=headers)

        # Update session ID from response
        if "mcp-session-id" in response.headers:
            self.session_id = response.headers["mcp-session-id"]

        # Parse response based on content type
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        elif "text/event-stream" in content_type:
            # Parse SSE format
            for line in response.text.strip().split("\n"):
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
        return {}

    def initialize(self) -> dict[str, Any]:
        """Initialize the MCP session."""
        return self.send(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        )


class TestMCPInitialize:
    """Test MCP initialize method."""

    def test_initialize_returns_server_info(self, mcp_client: MCPClient):
        """Test initialize returns server info and capabilities."""
        response = mcp_client.initialize()

        assert "result" in response, f"Expected result, got: {response}"
        result = response["result"]

        # Check required fields
        assert "protocolVersion" in result
        assert "serverInfo" in result
        assert "capabilities" in result

        # Check server info
        server_info = result["serverInfo"]
        assert "name" in server_info
        assert "version" in server_info

    def test_initialize_sets_session(self, mcp_client: MCPClient):
        """Test initialize creates a session."""
        mcp_client.initialize()

        # Session ID should be set after initialize
        assert mcp_client.session_id is not None


class TestMCPTools:
    """Test MCP tools methods."""

    def test_tools_list_returns_tools(self, mcp_client: MCPClient):
        """Test tools/list returns available tools."""
        mcp_client.initialize()
        response = mcp_client.send("tools/list", {})

        assert "result" in response, f"Expected result, got: {response}"
        result = response["result"]
        assert "tools" in result

        tools = result["tools"]
        assert isinstance(tools, list)

        # Should have at least the built-in ping tool
        tool_names = [t["name"] for t in tools]
        assert "k8s_ping" in tool_names

    def test_tools_call_ping(self, mcp_client: MCPClient):
        """Test calling the k8s_ping tool."""
        mcp_client.initialize()
        response = mcp_client.send(
            "tools/call",
            {"name": "k8s_ping", "arguments": {}},
        )

        assert "result" in response, f"Expected result, got: {response}"
        result = response["result"]
        assert "content" in result

        content = result["content"]
        assert len(content) > 0
        assert content[0]["type"] == "text"
        assert "pong" in content[0]["text"]

    def test_tools_call_unknown_tool_returns_error(self, mcp_client: MCPClient):
        """Test calling unknown tool returns error."""
        mcp_client.initialize()
        response = mcp_client.send(
            "tools/call",
            {"name": "nonexistent_tool", "arguments": {}},
        )

        # Should return an error
        assert "error" in response or (
            "result" in response and response["result"].get("isError")
        ), f"Expected error, got: {response}"


class TestMCPPrompts:
    """Test MCP prompts methods."""

    def test_prompts_list_returns_prompts(self, mcp_client: MCPClient):
        """Test prompts/list returns available prompts."""
        mcp_client.initialize()
        response = mcp_client.send("prompts/list", {})

        assert "result" in response, f"Expected result, got: {response}"
        result = response["result"]
        assert "prompts" in result

        prompts = result["prompts"]
        assert isinstance(prompts, list)
        assert len(prompts) > 0  # We register 9 prompts

    def test_prompts_get_resource_status(self, mcp_client: MCPClient):
        """Test getting the resource status prompt."""
        mcp_client.initialize()
        response = mcp_client.send(
            "prompts/get",
            {"name": "k8s_resource_status", "arguments": {"resource_type": "pods"}},
        )

        assert "result" in response, f"Expected result, got: {response}"
        result = response["result"]
        assert "messages" in result

        messages = result["messages"]
        assert len(messages) > 0
        assert messages[0]["role"] in ("user", "assistant")


class TestMCPResources:
    """Test MCP resources methods."""

    def test_resources_list_returns_resources(self, mcp_client: MCPClient):
        """Test resources/list returns available resources."""
        mcp_client.initialize()
        response = mcp_client.send("resources/list", {})

        assert "result" in response, f"Expected result, got: {response}"
        result = response["result"]
        assert "resources" in result

        resources = result["resources"]
        assert isinstance(resources, list)

        # Should have our cluster resources
        uris = [r["uri"] for r in resources]
        assert "k8s://cluster/context" in uris
        assert "k8s://cluster/namespaces" in uris
        assert "k8s://cluster/info" in uris

    def test_resources_read_context(self, mcp_client: MCPClient):
        """Test reading the cluster context resource."""
        mcp_client.initialize()
        response = mcp_client.send(
            "resources/read",
            {"uri": "k8s://cluster/context"},
        )

        assert "result" in response, f"Expected result, got: {response}"
        result = response["result"]
        assert "contents" in result

        contents = result["contents"]
        assert len(contents) > 0

        # Content should be JSON
        content = contents[0]
        assert "text" in content
        data = json.loads(content["text"])
        assert "current_context" in data or "error" in data


class TestMCPSessionHandling:
    """Test MCP session handling."""

    def test_request_without_session_fails(self, client: httpx.Client):
        """Test that requests without initialize fail."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }
        response = client.post(
            "/mcp",
            json=request,
            headers={"Accept": "application/json"},
        )

        # Should return 400 or error response
        if response.status_code == 200:
            data = response.json()
            assert "error" in data

    def test_session_persists_across_requests(self, mcp_client: MCPClient):
        """Test that session persists across multiple requests."""
        mcp_client.initialize()
        session_id = mcp_client.session_id

        # Make another request
        mcp_client.send("tools/list", {})

        # Session ID should be the same
        assert mcp_client.session_id == session_id


class TestJSONRPCCompliance:
    """Test JSON-RPC 2.0 compliance."""

    def test_response_includes_jsonrpc_version(self, mcp_client: MCPClient):
        """Test response includes jsonrpc version."""
        response = mcp_client.initialize()

        assert response.get("jsonrpc") == "2.0"

    def test_response_includes_matching_id(self, mcp_client: MCPClient):
        """Test response includes matching request ID."""
        mcp_client.request_id = 42
        response = mcp_client.send(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        )

        assert response.get("id") == 43  # request_id increments before use

    def test_invalid_method_returns_error(self, mcp_client: MCPClient):
        """Test invalid method returns JSON-RPC error."""
        mcp_client.initialize()
        response = mcp_client.send("invalid/method", {})

        # Should have error
        assert "error" in response
        error = response["error"]
        assert "code" in error
        assert "message" in error


@pytest.fixture
def mcp_client(client: httpx.Client) -> MCPClient:
    """Create an MCP client for testing."""
    return MCPClient(client)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
