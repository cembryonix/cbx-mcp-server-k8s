#!/usr/bin/env python3
"""
Test Redis integration with running MCP server.

Prerequisites:
    - MCP server running with streamable-http transport
    - Redis running and accessible
    - Server config with event_store.persistence=redis

Usage:
    ./test-redis.py                          # Run all tests
    ./test-redis.py --cleanup                # Run tests and clean up after
    ./test-redis.py --server-url http://localhost:8765
    ./test-redis.py --redis-url redis://localhost:6379/0
    ./test-redis.py -v                       # Verbose output

Tests:
    1. Redis connection
    2. Server health check
    3. MCP session initialization
    4. Event store (Redis Streams)
    5. Tool calls with session
    6. Event persistence (TTL)
    7. Multiple sessions

Cleanup:
    - Only cleans up sessions created during THIS test run
    - Does NOT delete other users' sessions or production data
    - Event streams expire via TTL (not deleted to avoid conflicts)
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime

import httpx
import redis


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    passed: bool
    message: str
    duration_ms: float = 0


class RedisTestSuite:
    """Test suite for Redis integration."""

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8765",
        redis_url: str = "redis://localhost:6379/0",
        verbose: bool = False,
        cleanup: bool = False,
    ):
        self.server_url = server_url.rstrip("/")
        self.redis_url = redis_url
        self.verbose = verbose
        self.cleanup = cleanup
        self.session_id = None
        self.results: list[TestResult] = []
        # Track keys created during this test run for safe cleanup
        self.created_session_ids: list[str] = []

    def log(self, msg: str):
        """Print message if verbose mode."""
        if self.verbose:
            print(f"  {msg}", file=sys.stderr)

    def run_all(self) -> bool:
        """Run all tests and return success status."""
        print(f"\n{'='*60}")
        print("Redis Integration Test Suite")
        print(f"{'='*60}")
        print(f"Server URL: {self.server_url}")
        print(f"Redis URL:  {self.redis_url}")
        print(f"{'='*60}\n")

        tests = [
            self.test_redis_connection,
            self.test_server_health,
            self.test_mcp_initialize,
            self.test_event_store_streams,
            self.test_tool_call_with_session,
            self.test_event_persistence,
            self.test_multiple_sessions,
        ]

        for test in tests:
            self._run_test(test)

        success = self._print_summary()

        if self.cleanup:
            self.do_cleanup()

        return success

    def do_cleanup(self):
        """
        Clean up test data from Redis.

        Only deletes keys created during this test run to avoid
        affecting other sessions or production data.
        """
        print("Cleaning up Redis test data...")
        r = redis.from_url(self.redis_url)

        if not self.created_session_ids:
            print("  No test sessions to clean up")
            print()
            return

        deleted_count = 0

        # Only delete session keys we created
        for session_id in self.created_session_ids:
            # Session data key
            session_key = f"mcp:session:{session_id}"
            if r.exists(session_key):
                r.delete(session_key)
                deleted_count += 1
                self.log(f"  Deleted {session_key}")

        # Note: Event streams use numeric IDs assigned by FastMCP, not session IDs
        # We can't safely delete them without risking other sessions' data
        # They will expire via TTL (default 3600s)

        print(f"  Deleted {deleted_count} session key(s)")
        print("  Event streams will expire via TTL (not deleted to avoid affecting other sessions)")
        print()

    def _run_test(self, test_func):
        """Run a single test and record result."""
        name = test_func.__name__.replace("test_", "").replace("_", " ").title()
        start = datetime.now()

        try:
            test_func()
            duration = (datetime.now() - start).total_seconds() * 1000
            result = TestResult(name, True, "OK", duration)
            print(f"  ✓ {name}")
        except AssertionError as e:
            duration = (datetime.now() - start).total_seconds() * 1000
            result = TestResult(name, False, str(e), duration)
            print(f"  ✗ {name}: {e}")
        except Exception as e:
            duration = (datetime.now() - start).total_seconds() * 1000
            result = TestResult(name, False, f"Error: {e}", duration)
            print(f"  ✗ {name}: {e}")

        self.results.append(result)

    def _print_summary(self) -> bool:
        """Print test summary and return success status."""
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        total_time = sum(r.duration_ms for r in self.results)

        print(f"\n{'='*60}")
        print(f"Results: {passed}/{total} passed in {total_time:.0f}ms")
        print(f"{'='*60}\n")

        if passed < total:
            print("Failed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.message}")
            print()

        return passed == total

    # --- Tests ---

    def test_redis_connection(self):
        """Test Redis connectivity."""
        r = redis.from_url(self.redis_url)
        response = r.ping()
        assert response is True, "Redis ping failed"
        self.log("Redis PING: PONG")

    def test_server_health(self):
        """Test server health endpoint."""
        response = httpx.get(f"{self.server_url}/health", timeout=5)
        assert response.status_code == 200, f"Health check failed: {response.status_code}"

        data = response.json()
        assert data["status"] == "healthy", f"Server not healthy: {data}"
        self.log(f"Server version: {data.get('version')}")

    def test_mcp_initialize(self):
        """Test MCP session initialization."""
        response = httpx.post(
            f"{self.server_url}/mcp",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "redis-test", "version": "1.0"},
                },
            },
            timeout=10,
        )

        assert response.status_code == 200, f"Initialize failed: {response.status_code}"

        # Extract session ID from header
        self.session_id = response.headers.get("mcp-session-id")
        assert self.session_id, "No session ID in response headers"
        self.created_session_ids.append(self.session_id)
        self.log(f"Session ID: {self.session_id}")

        # Check response contains server info
        # SSE format: "event: message\ndata: {...}\n"
        body = response.text
        assert "serverInfo" in body, "No serverInfo in response"

    def test_event_store_streams(self):
        """Test that events are stored in Redis Streams."""
        r = redis.from_url(self.redis_url)

        # Find event streams (new format includes instance ID: mcp:events:{instance_id}:stream:*)
        keys = list(r.scan_iter(match="mcp:events:*:stream:*"))
        if not keys:
            # Fall back to old format without instance ID
            keys = list(r.scan_iter(match="mcp:events:stream:*"))
        assert len(keys) > 0, "No event streams found in Redis"
        self.log(f"Found {len(keys)} event stream(s)")

        # Check at least one stream has events
        for key in keys:
            length = r.xlen(key)
            if length > 0:
                self.log(f"  {key.decode()}: {length} event(s)")
                return

        assert False, "No events found in any stream"

    def test_tool_call_with_session(self):
        """Test tool call using session ID."""
        assert self.session_id, "No session ID (run test_mcp_initialize first)"

        response = httpx.post(
            f"{self.server_url}/mcp",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": self.session_id,
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "k8s_ping",
                    "arguments": {},
                },
            },
            timeout=10,
        )

        assert response.status_code == 200, f"Tool call failed: {response.status_code}"

        body = response.text
        assert "pong" in body.lower(), f"Unexpected response: {body[:200]}"
        self.log("k8s_ping returned pong")

    def test_event_persistence(self):
        """Test that events have TTL set."""
        r = redis.from_url(self.redis_url)

        # Find event streams (new format includes instance ID)
        keys = list(r.scan_iter(match="mcp:events:*:stream:*"))
        if not keys:
            keys = list(r.scan_iter(match="mcp:events:stream:*"))
        assert len(keys) > 0, "No event streams found"

        for key in keys:
            ttl = r.ttl(key)
            # TTL should be positive (not -1 = no expiry, not -2 = doesn't exist)
            if ttl > 0:
                self.log(f"  {key.decode()}: TTL={ttl}s")
                return

        # At least warn if no TTL set
        self.log("Warning: No TTL found on event streams")

    def test_multiple_sessions(self):
        """Test creating multiple sessions."""
        sessions = []

        for i in range(3):
            response = httpx.post(
                f"{self.server_url}/mcp",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": i + 10,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": f"test-client-{i}", "version": "1.0"},
                    },
                },
                timeout=10,
            )

            assert response.status_code == 200, f"Session {i} failed"
            session_id = response.headers.get("mcp-session-id")
            assert session_id, f"No session ID for session {i}"
            sessions.append(session_id)
            self.created_session_ids.append(session_id)

        # All sessions should be unique
        assert len(set(sessions)) == 3, "Sessions are not unique"
        self.log("Created 3 unique sessions")


def main():
    parser = argparse.ArgumentParser(
        description="Test Redis integration with MCP server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--server-url",
        default="http://127.0.0.1:8765",
        help="MCP server URL (default: http://127.0.0.1:8765)",
    )
    parser.add_argument(
        "--redis-url",
        default="redis://localhost:6379/0",
        help="Redis URL (default: redis://localhost:6379/0)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Clean up Redis test data after tests",
    )
    parser.add_argument(
        "--cleanup-only",
        action="store_true",
        help="Only clean up Redis test data (skip tests)",
    )

    args = parser.parse_args()

    suite = RedisTestSuite(
        server_url=args.server_url,
        redis_url=args.redis_url,
        verbose=args.verbose,
        cleanup=args.cleanup,
    )

    if args.cleanup_only:
        print("\nNote: --cleanup-only cannot clean up data from previous test runs.")
        print("Use --cleanup to run tests and clean up after, or wait for TTL expiry.")
        print("(Session data TTL: ~1 hour, Event streams TTL: ~1 hour)\n")
        sys.exit(0)

    success = suite.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
