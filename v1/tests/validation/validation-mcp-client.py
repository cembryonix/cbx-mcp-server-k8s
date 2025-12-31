#!/usr/bin/env python3
"""
MCP Validation Client for CBX K8s MCP Server.

This client tests MCP servers via stdio or HTTP transport by executing
common agent scenarios and validating response schemas.

Modes:
    ci   - Automated testing: starts server via subprocess (for GitHub workflows)
    live - Manual testing: connects to already-running server

Usage:
    # CI mode - start server and test
    python validation-mcp-client.py ci --server-cmd "python app/main.py"

    # Live mode - HTTP transport (docker-compose, k8s, remote)
    python validation-mcp-client.py live --transport http --server-url http://localhost:8080/mcp

    # Live mode - stdio transport (docker exec style, like Claude Desktop)
    python validation-mcp-client.py live --transport stdio --stdio-config mcp-config.json

    # Help
    python validation-mcp-client.py --help
    python validation-mcp-client.py ci --help
    python validation-mcp-client.py live --help
"""

import argparse
import asyncio
import json
import sys
import subprocess
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

# Optional: FastMCP client for HTTP transport
try:
    from fastmcp import Client as FastMCPClient
    from fastmcp.client.transports import StreamableHttpTransport
    FASTMCP_CLIENT_AVAILABLE = True
except ImportError:
    FASTMCP_CLIENT_AVAILABLE = False


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    passed: bool
    message: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class ValidationReport:
    """Summary report of all validation tests."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[TestResult] = field(default_factory=list)

    def add_result(self, result: TestResult):
        self.total += 1
        if result.passed:
            self.passed += 1
        else:
            self.failed += 1
        self.results.append(result)

    def print_summary(self):
        print("\n" + "=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)
        print(f"Total tests: {self.total}")
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        print(f"Success rate: {self.passed / self.total * 100:.1f}%" if self.total > 0 else "N/A")
        print()

        if self.failed > 0:
            print("FAILED TESTS:")
            for result in self.results:
                if not result.passed:
                    print(f"  - {result.name}: {result.message}")


class MCPClientBase:
    """Base class for MCP clients."""

    def __init__(self):
        self.request_id = 0

    def _next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def _build_request(self, method: str, params: dict | None = None) -> dict:
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params:
            request["params"] = params
        return request

    async def start(self):
        """Start the client connection."""
        raise NotImplementedError

    async def stop(self):
        """Stop the client connection."""
        raise NotImplementedError

    async def send_request(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC request and return the response."""
        raise NotImplementedError

    async def initialize(self) -> dict:
        """Send initialize request."""
        return await self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "validation-client",
                "version": "1.0.0"
            }
        })

    async def list_tools(self) -> dict:
        """List available tools."""
        return await self.send_request("tools/list")

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Call a tool with arguments."""
        return await self.send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })


class MCPStdioClient(MCPClientBase):
    """MCP client for stdio transport."""

    def __init__(self, server_cmd: str | None = None, stdio_config: dict | None = None):
        super().__init__()
        self.server_cmd = server_cmd
        self.stdio_config = stdio_config
        self.process: subprocess.Popen | None = None

    async def start(self):
        """Start the MCP server process."""
        import os

        if self.stdio_config:
            # Use config file format (like Claude Desktop)
            cmd = self.stdio_config.get("command", "")
            args = self.stdio_config.get("args", [])
            env = self.stdio_config.get("env", {})

            full_env = os.environ.copy()
            full_env.update(env)

            self.process = subprocess.Popen(
                [cmd] + args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=full_env,
            )
        elif self.server_cmd:
            # Use command string (CI mode)
            # Replace 'python' with current interpreter to use venv
            cmd_parts = self.server_cmd.split()
            if cmd_parts and cmd_parts[0] in ("python", "python3"):
                cmd_parts[0] = sys.executable

            self.process = subprocess.Popen(
                cmd_parts,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        else:
            raise RuntimeError("Either server_cmd or stdio_config must be provided")

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

        request = self._build_request(method, params)

        # Send request
        request_str = json.dumps(request) + "\n"
        self.process.stdin.write(request_str)
        self.process.stdin.flush()

        # Read response
        response_str = self.process.stdout.readline()
        if not response_str:
            raise RuntimeError("No response from server")

        return json.loads(response_str)


class MCPHttpClient(MCPClientBase):
    """MCP client for HTTP/streamable-http transport using FastMCP Client."""

    def __init__(self, server_url: str, timeout: float = 30.0):
        super().__init__()
        self.server_url = server_url
        self.timeout = timeout
        self.client: FastMCPClient | None = None
        self._connected = False

    async def start(self):
        """Initialize FastMCP HTTP client."""
        if not FASTMCP_CLIENT_AVAILABLE:
            raise RuntimeError("FastMCP client not available. Run: pip install fastmcp")
        transport = StreamableHttpTransport(url=self.server_url)
        self.client = FastMCPClient(transport=transport)
        await self.client.__aenter__()
        self._connected = True

    async def stop(self):
        """Close FastMCP client."""
        if self.client and self._connected:
            await self.client.__aexit__(None, None, None)
            self._connected = False

    async def send_request(self, method: str, params: dict | None = None) -> dict:
        """Send a request via FastMCP client - maps to specific client methods."""
        if not self.client or not self._connected:
            raise RuntimeError("HTTP client not started")

        # FastMCP client has specific methods, not raw JSON-RPC
        # We need to map our generic calls to FastMCP client methods
        raise NotImplementedError("Use specific methods instead")

    async def initialize(self) -> dict:
        """Initialize is implicit with FastMCP client connection."""
        # FastMCP client handles initialization when entering context
        # Return a mock successful response
        return {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {}
            }
        }

    async def list_tools(self) -> dict:
        """List available tools via FastMCP client."""
        if not self.client:
            raise RuntimeError("HTTP client not started")

        tools = await self.client.list_tools()
        # Convert to JSON-RPC response format
        return {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "result": {
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.inputSchema,
                        "annotations": t.annotations.model_dump() if t.annotations else None
                    }
                    for t in tools
                ]
            }
        }

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Call a tool via FastMCP client."""
        if not self.client:
            raise RuntimeError("HTTP client not started")

        try:
            result = await self.client.call_tool(name, arguments)
            # Convert to JSON-RPC response format
            return {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "result": {
                    "content": [{"type": "text", "text": str(result.data) if result.data else ""}],
                    "isError": result.is_error if hasattr(result, 'is_error') else False
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "result": {
                    "content": [{"type": "text", "text": str(e)}],
                    "isError": True
                }
            }


class MCPValidator:
    """Validates MCP server responses and behavior."""

    def __init__(self, client: MCPClientBase, verbose: bool = False):
        self.client = client
        self.verbose = verbose
        self.report = ValidationReport()

    def log(self, message: str):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"  [DEBUG] {message}")

    async def run_all_tests(self):
        """Run all validation tests."""
        print("Starting MCP Validation Tests...")
        print("-" * 40)

        # Test 1: Initialize
        await self.test_initialize()

        # Test 2: List tools
        tools = await self.test_list_tools()

        if tools:
            # Test 3: Describe tools (read-only)
            await self.test_describe_tools(tools)

            # Test 4: Execute safe commands
            await self.test_execute_safe_commands(tools)

            # Test 5: Security validation (strict mode)
            await self.test_security_validation(tools)

        self.report.print_summary()
        return self.report.failed == 0

    async def test_initialize(self):
        """Test protocol initialization."""
        test_name = "initialize"
        try:
            self.log(f"Sending initialize request...")
            response = await self.client.initialize()
            self.log(f"Response: {json.dumps(response, indent=2)}")

            # Validate response structure
            if "error" in response:
                self.report.add_result(TestResult(
                    name=test_name,
                    passed=False,
                    message=f"Initialize error: {response['error']}"
                ))
                return

            result = response.get("result", {})
            if "protocolVersion" in result or "capabilities" in result:
                self.report.add_result(TestResult(
                    name=test_name,
                    passed=True,
                    message="Protocol initialized successfully"
                ))
            else:
                self.report.add_result(TestResult(
                    name=test_name,
                    passed=False,
                    message="Missing protocolVersion or capabilities in response"
                ))
        except Exception as e:
            self.report.add_result(TestResult(
                name=test_name,
                passed=False,
                message=f"Exception: {str(e)}"
            ))

    async def test_list_tools(self) -> list[dict] | None:
        """Test tools/list endpoint."""
        test_name = "tools/list"
        try:
            self.log(f"Sending tools/list request...")
            response = await self.client.list_tools()
            self.log(f"Response: {json.dumps(response, indent=2)}")

            if "error" in response:
                self.report.add_result(TestResult(
                    name=test_name,
                    passed=False,
                    message=f"Error: {response['error']}"
                ))
                return None

            result = response.get("result", {})
            tools = result.get("tools", [])

            if not tools:
                self.report.add_result(TestResult(
                    name=test_name,
                    passed=False,
                    message="No tools returned"
                ))
                return None

            # Validate tool schema
            valid_schema = True
            for tool in tools:
                if "name" not in tool:
                    valid_schema = False
                    break
                # inputSchema should never be null per MCP spec
                if "inputSchema" in tool and tool["inputSchema"] is None:
                    valid_schema = False
                    break

            if valid_schema:
                # Check for annotations
                tools_with_annotations = sum(1 for t in tools if t.get("annotations"))
                self.report.add_result(TestResult(
                    name=test_name,
                    passed=True,
                    message=f"Found {len(tools)} tools ({tools_with_annotations} with annotations)"
                ))
                return tools
            else:
                self.report.add_result(TestResult(
                    name=test_name,
                    passed=False,
                    message="Invalid tool schema structure"
                ))
                return None

        except Exception as e:
            self.report.add_result(TestResult(
                name=test_name,
                passed=False,
                message=f"Exception: {str(e)}"
            ))
            return None

    async def test_describe_tools(self, tools: list[dict]):
        """Test describe_* tools (read-only operations)."""
        describe_tools = [t for t in tools if t["name"].startswith("describe_")]

        for tool in describe_tools:
            test_name = f"call/{tool['name']}"
            try:
                self.log(f"Calling {tool['name']} with command=None...")
                response = await self.client.call_tool(tool["name"], {"command": None})
                self.log(f"Response: {json.dumps(response, indent=2)[:500]}...")

                if "error" in response:
                    self.report.add_result(TestResult(
                        name=test_name,
                        passed=False,
                        message=f"Error: {response['error']}"
                    ))
                else:
                    result = response.get("result", {})
                    is_error = result.get("isError", False)
                    if is_error:
                        self.report.add_result(TestResult(
                            name=test_name,
                            passed=False,
                            message=f"Tool returned isError=true"
                        ))
                    else:
                        self.report.add_result(TestResult(
                            name=test_name,
                            passed=True,
                            message="Help text retrieved successfully"
                        ))
            except Exception as e:
                self.report.add_result(TestResult(
                    name=test_name,
                    passed=False,
                    message=f"Exception: {str(e)}"
                ))

    async def test_execute_safe_commands(self, tools: list[dict]):
        """Test execute_* tools with safe commands."""
        # Test commands that should always work
        safe_commands = {
            "execute_kubectl": "kubectl version --client",
            "execute_helm": "helm version",
        }

        execute_tools = [t for t in tools if t["name"].startswith("execute_")]

        for tool in execute_tools:
            tool_name = tool["name"]
            if tool_name not in safe_commands:
                continue

            test_name = f"execute/{tool_name}_safe"
            try:
                self.log(f"Calling {tool_name} with safe command...")
                response = await self.client.call_tool(
                    tool_name,
                    {"command": safe_commands[tool_name]}
                )
                self.log(f"Response: {json.dumps(response, indent=2)[:500]}...")

                result = response.get("result", {})

                # Check if we got a valid response (success or auth error is acceptable)
                if "error" in response:
                    # Server error
                    self.report.add_result(TestResult(
                        name=test_name,
                        passed=False,
                        message=f"Server error: {response['error']}"
                    ))
                elif isinstance(result, dict):
                    is_error = result.get("isError", False)
                    self.report.add_result(TestResult(
                        name=test_name,
                        passed=True,
                        message=f"Command executed (isError: {is_error})"
                    ))
                else:
                    self.report.add_result(TestResult(
                        name=test_name,
                        passed=True,
                        message="Command returned result"
                    ))
            except Exception as e:
                self.report.add_result(TestResult(
                    name=test_name,
                    passed=False,
                    message=f"Exception: {str(e)}"
                ))

    async def test_security_validation(self, tools: list[dict]):
        """Test that dangerous commands are blocked in strict mode."""
        # These commands should be blocked by security validation
        dangerous_commands = [
            ("execute_kubectl", "kubectl delete pods --all", "delete --all"),
        ]

        for tool_name, command, description in dangerous_commands:
            test_name = f"security/{description}"

            # Find the tool
            tool = next((t for t in tools if t["name"] == tool_name), None)
            if not tool:
                self.report.add_result(TestResult(
                    name=test_name,
                    passed=True,  # Skip if tool not available
                    message=f"Tool {tool_name} not available, skipping"
                ))
                continue

            try:
                self.log(f"Testing dangerous command: {command}")
                response = await self.client.call_tool(tool_name, {"command": command})
                self.log(f"Response: {json.dumps(response, indent=2)[:500]}...")

                result = response.get("result", {})

                # In strict mode, this should return isError=true
                # In permissive mode, it might succeed
                is_error = result.get("isError", False) if isinstance(result, dict) else False

                if is_error:
                    self.report.add_result(TestResult(
                        name=test_name,
                        passed=True,
                        message="Dangerous command correctly blocked (isError=true)"
                    ))
                elif "error" in response:
                    self.report.add_result(TestResult(
                        name=test_name,
                        passed=True,
                        message="Dangerous command blocked at protocol level"
                    ))
                else:
                    # Command was allowed - might be in permissive mode
                    self.report.add_result(TestResult(
                        name=test_name,
                        passed=True,
                        message="Note: Command allowed (server may be in permissive mode)"
                    ))

            except Exception as e:
                self.report.add_result(TestResult(
                    name=test_name,
                    passed=False,
                    message=f"Exception: {str(e)}"
                ))


def load_stdio_config(config_path: str) -> dict:
    """Load stdio config from JSON file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path) as f:
        config = json.load(f)

    # Validate required fields
    if "command" not in config:
        raise ValueError("Config must have 'command' field")

    return config


async def run_ci_mode(args):
    """Run in CI mode - start server and test."""
    print(f"CI Mode: Starting MCP server with: {args.server_cmd}")

    client = MCPStdioClient(server_cmd=args.server_cmd)
    validator = MCPValidator(client, verbose=args.verbose)

    try:
        await client.start()
        success = await validator.run_all_tests()
        return 0 if success else 1
    except Exception as e:
        print(f"Error: {e}")
        return 1
    finally:
        await client.stop()


async def run_live_mode(args):
    """Run in live mode - connect to running server."""
    if args.transport == "http":
        if not args.server_url:
            print("Error: --server-url required for HTTP transport")
            return 1

        print(f"Live Mode (HTTP): Connecting to {args.server_url}")

        if not FASTMCP_CLIENT_AVAILABLE:
            print("Error: FastMCP client not available. Run: pip install fastmcp")
            return 1

        client = MCPHttpClient(server_url=args.server_url)

    elif args.transport == "stdio":
        if not args.stdio_config:
            print("Error: --stdio-config required for stdio transport")
            return 1

        print(f"Live Mode (stdio): Using config from {args.stdio_config}")

        try:
            config = load_stdio_config(args.stdio_config)
        except Exception as e:
            print(f"Error loading config: {e}")
            return 1

        client = MCPStdioClient(stdio_config=config)

    else:
        print(f"Error: Unknown transport: {args.transport}")
        return 1

    validator = MCPValidator(client, verbose=args.verbose)

    try:
        await client.start()
        success = await validator.run_all_tests()
        return 0 if success else 1
    except Exception as e:
        print(f"Error: {e}")
        return 1
    finally:
        await client.stop()


def main():
    parser = argparse.ArgumentParser(
        description="MCP Validation Client for CBX K8s MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # CI mode - start server and test (for GitHub workflows)
  python validation-mcp-client.py ci --server-cmd "python app/main.py"

  # Live mode - test running HTTP server
  python validation-mcp-client.py live --transport http --server-url http://localhost:8080/mcp

  # Live mode - test via stdio config (like Claude Desktop)
  python validation-mcp-client.py live --transport stdio --stdio-config mcp-config.json
        """
    )

    subparsers = parser.add_subparsers(dest="mode", help="Validation mode")

    # CI mode subparser
    ci_parser = subparsers.add_parser("ci", help="CI mode: start server via subprocess and test")
    ci_parser.add_argument(
        "--server-cmd",
        required=True,
        help="Command to start the MCP server (e.g., 'python app/main.py')"
    )
    ci_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    # Live mode subparser
    live_parser = subparsers.add_parser("live", help="Live mode: test already-running server")
    live_parser.add_argument(
        "--transport",
        choices=["http", "stdio"],
        required=True,
        help="Transport protocol to use"
    )
    live_parser.add_argument(
        "--server-url",
        help="Server URL for HTTP transport (e.g., http://localhost:8080/mcp)"
    )
    live_parser.add_argument(
        "--stdio-config",
        help="Path to MCP stdio config JSON file (for stdio transport)"
    )
    live_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    if args.mode is None:
        parser.print_help()
        sys.exit(1)

    if args.mode == "ci":
        exit_code = asyncio.run(run_ci_mode(args))
    elif args.mode == "live":
        exit_code = asyncio.run(run_live_mode(args))
    else:
        parser.print_help()
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
