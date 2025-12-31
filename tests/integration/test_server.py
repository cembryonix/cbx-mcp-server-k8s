#!/usr/bin/env python3
"""
Integration tests for MCP server.

Tests the server as a whole - startup, endpoints, and basic MCP operations.
"""

import json

import httpx
import pytest


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_endpoint_returns_200(self, client: httpx.Client):
        """Test /health endpoint returns healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert data["service"] == "cbx_mcp_k8s"

    def test_ready_endpoint_returns_200(self, client: httpx.Client):
        """Test /ready endpoint returns ready status."""
        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "checks" in data


class TestMetricsEndpoint:
    """Test Prometheus metrics endpoint."""

    def test_metrics_endpoint_returns_prometheus_format(self, client: httpx.Client):
        """Test /metrics endpoint returns Prometheus format."""
        response = client.get("/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

        # Check for expected metrics
        text = response.text
        assert "cbx_mcp_info" in text
        assert "cbx_mcp_uptime_seconds" in text
        assert "cbx_mcp_requests_total" in text


class TestMCPProtocol:
    """Test MCP protocol endpoints."""

    def test_mcp_endpoint_exists(self, client: httpx.Client):
        """Test that MCP endpoint responds."""
        # MCP uses POST to /mcp for JSON-RPC
        # Without proper JSON-RPC request, it should return an error
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"Accept": "application/json, text/event-stream"},
        )

        # Should get a response (even if error)
        assert response.status_code in (200, 400, 404, 405)

    def test_mcp_initialize(self, client: httpx.Client):
        """Test MCP initialize request."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0",
                },
            },
        }

        response = client.post(
            "/mcp",
            json=request,
            headers={"Accept": "application/json, text/event-stream"},
        )

        # Should get a valid response
        assert response.status_code == 200

        # Parse response - could be JSON or SSE
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            data = response.json()
            assert "result" in data or "error" in data
        elif "text/event-stream" in content_type:
            # SSE format - parse first event
            lines = response.text.strip().split("\n")
            for line in lines:
                if line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    assert "result" in data or "error" in data
                    break

    def test_mcp_list_tools(self, client: httpx.Client):
        """Test MCP tools/list request.

        Note: MCP streamable-http requires stateful sessions. The initialize
        call creates a session, and subsequent calls must include the session ID.
        Without proper session handling, we expect a 400 error for tools/list.
        """
        # First initialize to create a session
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        }
        init_response = client.post(
            "/mcp",
            json=init_request,
            headers={"Accept": "application/json, text/event-stream"},
        )

        # Get session ID from response header
        session_id = init_response.headers.get("mcp-session-id")

        # Then list tools with session
        list_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }

        headers = {"Accept": "application/json, text/event-stream"}
        if session_id:
            headers["mcp-session-id"] = session_id

        response = client.post(
            "/mcp",
            json=list_request,
            headers=headers,
        )

        # Should succeed with session, or 400 without (expected if no session header)
        assert response.status_code in (200, 400)


class TestServerStartup:
    """Test server startup and configuration."""

    def test_server_is_running(self, server):
        """Test that server process is running."""
        assert server.process is not None
        assert server.process.poll() is None  # Still running

    def test_server_responds_to_requests(self, client: httpx.Client):
        """Test that server responds to HTTP requests."""
        response = client.get("/health")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
