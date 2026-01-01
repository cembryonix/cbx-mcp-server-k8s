#!/usr/bin/env python3
"""
MCP Server Validation Client

Validates MCP server compatibility from an external client perspective.
Uses langchain_mcp_adapters to simulate how AI agents interact with the server.

Usage:
    # Test against default config
    python validation_client.py

    # Test against custom URL
    python validation_client.py --url http://localhost:8080/mcp

    # Test specific categories
    python validation_client.py --category protocol
    python validation_client.py --category read-only
    python validation_client.py --category actions

    # Verbose output
    python validation_client.py -v

    # List available tests
    python validation_client.py --list
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from langchain_mcp_adapters.client import MultiServerMCPClient


class TestStatus(Enum):
    """Status of a test."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


@dataclass
class TestResult:
    """Result of a single test."""

    name: str
    status: TestStatus
    message: str
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestCase:
    """A single test case loaded from YAML."""

    name: str
    description: str
    category: str
    tool: str | None = None
    command: str | None = None
    action: str | None = None  # For protocol tests
    expect: dict[str, Any] = field(default_factory=dict)
    skip_if_no_repo: bool = False
    skip_if_no_app: bool = False
    cleanup: bool = False


@dataclass
class ValidationConfig:
    """Configuration for validation client."""

    url: str = "http://127.0.0.1:8080/mcp"
    transport: str = "streamable_http"
    timeout: int = 30
    verbose: bool = False
    fail_fast: bool = False
    categories: list[str] = field(default_factory=list)
    expected_tools: list[str] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> "ValidationConfig":
        """Load config from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        server = data.get("server", {})
        tests = data.get("tests", {})

        return cls(
            url=server.get("url", cls.url),
            transport=server.get("transport", cls.transport),
            timeout=server.get("timeout", cls.timeout),
            verbose=tests.get("verbose", cls.verbose),
            fail_fast=tests.get("fail_fast", cls.fail_fast),
            categories=tests.get("categories", []),
            expected_tools=data.get("expected_tools", []),
        )


class MCPValidationClient:
    """
    Validation client for testing MCP server compatibility.

    Uses langchain_mcp_adapters to connect to the server and validate
    that it works correctly from a LangChain agent perspective.
    """

    def __init__(self, config: ValidationConfig):
        self.config = config
        self.results: list[TestResult] = []
        self._client: MultiServerMCPClient | None = None
        self._tools: list[Any] = []
        self._tools_by_name: dict[str, Any] = {}

    def _log(self, message: str) -> None:
        """Log message if verbose mode enabled."""
        if self.config.verbose:
            print(f"  [DEBUG] {message}")

    async def connect(self) -> bool:
        """Connect to the MCP server."""
        try:
            self._log(f"Connecting to {self.config.url}")

            # langchain_mcp_adapters 0.2+ doesn't use context manager
            # Transport should be "http" for HTTP-based servers
            self._client = MultiServerMCPClient(
                {
                    "k8s": {
                        "url": self.config.url,
                        "transport": "http",
                    }
                }
            )

            # Test connection by getting tools
            self._tools = await self._client.get_tools()
            self._tools_by_name = {t.name: t for t in self._tools}
            self._log(f"Connected, found {len(self._tools)} tools")
            return True

        except Exception as e:
            self._log(f"Connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        # langchain_mcp_adapters handles cleanup automatically
        self._client = None
        self._tools = []
        self._tools_by_name = {}

    async def _get_tools(self) -> list[Any]:
        """Get available tools from the server."""
        if not self._client:
            raise RuntimeError("Not connected")

        if not self._tools:
            self._tools = self._client.get_tools()
            self._tools_by_name = {t.name: t for t in self._tools}
            self._log(f"Loaded {len(self._tools)} tools")

        return self._tools

    async def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call a tool and return the result."""
        if not self._client:
            raise RuntimeError("Not connected")

        tools = await self._get_tools()
        tool = self._tools_by_name.get(tool_name)

        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")

        # Use the tool's invoke method
        result = await tool.ainvoke(arguments)
        return {"content": result, "is_error": False}

    # =========================================================================
    # Protocol Tests
    # =========================================================================

    async def run_protocol_test(self, test: TestCase) -> TestResult:
        """Run a protocol-level test."""
        import time

        start = time.time()

        try:
            if test.action == "initialize":
                # Connection already validates initialization
                return TestResult(
                    name=test.name,
                    status=TestStatus.PASSED,
                    message="Protocol initialized successfully",
                    duration_ms=(time.time() - start) * 1000,
                )

            elif test.action == "tools_list":
                tools = await self._get_tools()
                min_count = test.expect.get("min_tool_count", 1)

                if len(tools) >= min_count:
                    return TestResult(
                        name=test.name,
                        status=TestStatus.PASSED,
                        message=f"Found {len(tools)} tools",
                        duration_ms=(time.time() - start) * 1000,
                        details={"tool_count": len(tools)},
                    )
                else:
                    return TestResult(
                        name=test.name,
                        status=TestStatus.FAILED,
                        message=f"Expected >= {min_count} tools, got {len(tools)}",
                        duration_ms=(time.time() - start) * 1000,
                    )

            elif test.action == "validate_schemas":
                tools = await self._get_tools()
                issues = []

                for tool in tools:
                    if not hasattr(tool, "name") or not tool.name:
                        issues.append(f"Tool missing name")
                    if not hasattr(tool, "args_schema"):
                        issues.append(f"{tool.name}: missing args_schema")

                if not issues:
                    return TestResult(
                        name=test.name,
                        status=TestStatus.PASSED,
                        message=f"All {len(tools)} tools have valid schemas",
                        duration_ms=(time.time() - start) * 1000,
                    )
                else:
                    return TestResult(
                        name=test.name,
                        status=TestStatus.FAILED,
                        message=f"Schema issues: {', '.join(issues[:3])}",
                        duration_ms=(time.time() - start) * 1000,
                        details={"issues": issues},
                    )

            elif test.action == "check_expected_tools":
                tools = await self._get_tools()
                tool_names = {t.name for t in tools}
                missing = []

                for expected in self.config.expected_tools:
                    if expected not in tool_names:
                        missing.append(expected)

                if not missing:
                    return TestResult(
                        name=test.name,
                        status=TestStatus.PASSED,
                        message=f"All {len(self.config.expected_tools)} expected tools present",
                        duration_ms=(time.time() - start) * 1000,
                    )
                else:
                    return TestResult(
                        name=test.name,
                        status=TestStatus.FAILED,
                        message=f"Missing tools: {', '.join(missing)}",
                        duration_ms=(time.time() - start) * 1000,
                        details={"missing": missing, "available": list(tool_names)},
                    )

            else:
                return TestResult(
                    name=test.name,
                    status=TestStatus.SKIPPED,
                    message=f"Unknown protocol action: {test.action}",
                    duration_ms=(time.time() - start) * 1000,
                )

        except Exception as e:
            return TestResult(
                name=test.name,
                status=TestStatus.ERROR,
                message=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    # =========================================================================
    # K8s Tool Tests
    # =========================================================================

    async def run_tool_test(self, test: TestCase) -> TestResult:
        """Run a K8s tool test."""
        import time

        start = time.time()

        try:
            # Check if tool exists
            tools = await self._get_tools()
            if test.tool not in self._tools_by_name:
                return TestResult(
                    name=test.name,
                    status=TestStatus.SKIPPED,
                    message=f"Tool not available: {test.tool}",
                    duration_ms=(time.time() - start) * 1000,
                )

            # Call the tool
            self._log(f"Calling {test.tool}: {test.command}")
            result = await self._call_tool(test.tool, {"command": test.command})

            content = result.get("content", "")
            is_error = result.get("is_error", False)

            # Check expectations
            expect_success = test.expect.get("success", True)
            output_contains = test.expect.get("output_contains")

            # Determine pass/fail
            if expect_success and is_error:
                return TestResult(
                    name=test.name,
                    status=TestStatus.FAILED,
                    message=f"Expected success but got error",
                    duration_ms=(time.time() - start) * 1000,
                    details={"output": str(content)[:500]},
                )

            if output_contains and output_contains not in str(content):
                return TestResult(
                    name=test.name,
                    status=TestStatus.FAILED,
                    message=f"Output missing expected: '{output_contains}'",
                    duration_ms=(time.time() - start) * 1000,
                    details={"output": str(content)[:500]},
                )

            return TestResult(
                name=test.name,
                status=TestStatus.PASSED,
                message=test.description,
                duration_ms=(time.time() - start) * 1000,
            )

        except Exception as e:
            return TestResult(
                name=test.name,
                status=TestStatus.ERROR,
                message=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    # =========================================================================
    # Test Loading and Running
    # =========================================================================

    def load_test_cases(self, test_dir: Path) -> list[TestCase]:
        """Load all test cases from YAML files."""
        test_cases = []

        for yaml_file in sorted(test_dir.glob("*.yaml")):
            self._log(f"Loading {yaml_file.name}")

            with open(yaml_file) as f:
                data = yaml.safe_load(f)

            category = data.get("category", yaml_file.stem)
            tests = data.get("tests", [])

            for test_data in tests:
                test = TestCase(
                    name=test_data.get("name", "unnamed"),
                    description=test_data.get("description", ""),
                    category=category,
                    tool=test_data.get("tool"),
                    command=test_data.get("command"),
                    action=test_data.get("action"),
                    expect=test_data.get("expect", {}),
                    skip_if_no_repo=test_data.get("skip_if_no_repo", False),
                    skip_if_no_app=test_data.get("skip_if_no_app", False),
                    cleanup=test_data.get("cleanup", False),
                )
                test_cases.append(test)

        return test_cases

    async def run_test(self, test: TestCase) -> TestResult:
        """Run a single test case."""
        if test.category == "protocol":
            return await self.run_protocol_test(test)
        else:
            return await self.run_tool_test(test)

    async def run_all_tests(self, test_dir: Path) -> list[TestResult]:
        """Run all validation tests."""
        print("\n" + "=" * 60)
        print("MCP Server Validation")
        print("=" * 60)
        print(f"Server: {self.config.url}")
        print(f"Transport: {self.config.transport}")
        print("=" * 60)

        # Connect
        print("\n[Connecting]")
        if not await self.connect():
            self.results.append(
                TestResult(
                    name="connection",
                    status=TestStatus.FAILED,
                    message=f"Failed to connect to {self.config.url}",
                )
            )
            self._print_summary()
            return self.results

        print("  Connected successfully")

        try:
            # Load test cases
            test_cases = self.load_test_cases(test_dir)
            print(f"\nLoaded {len(test_cases)} test cases")

            # Filter by category if specified
            if self.config.categories:
                test_cases = [
                    t for t in test_cases if t.category in self.config.categories
                ]
                print(f"Filtered to {len(test_cases)} tests (categories: {self.config.categories})")

            # Group by category
            categories: dict[str, list[TestCase]] = {}
            for test in test_cases:
                if test.category not in categories:
                    categories[test.category] = []
                categories[test.category].append(test)

            # Run tests by category
            for category, tests in categories.items():
                print(f"\n[{category}]")

                for test in tests:
                    result = await self.run_test(test)
                    self.results.append(result)

                    # Print result
                    icon = {
                        TestStatus.PASSED: "\033[32m✓\033[0m",
                        TestStatus.FAILED: "\033[31m✗\033[0m",
                        TestStatus.SKIPPED: "\033[33m○\033[0m",
                        TestStatus.ERROR: "\033[31m!\033[0m",
                    }.get(result.status, "?")

                    print(f"  {icon} {result.name}: {result.message}")

                    if self.config.verbose and result.details:
                        for key, value in result.details.items():
                            print(f"      {key}: {value}")

                    # Fail fast
                    if self.config.fail_fast and result.status in (
                        TestStatus.FAILED,
                        TestStatus.ERROR,
                    ):
                        print("\n  [Stopping due to fail_fast]")
                        break

        finally:
            await self.disconnect()

        self._print_summary()
        return self.results

    def _print_summary(self) -> None:
        """Print test summary."""
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)

        passed = sum(1 for r in self.results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in self.results if r.status == TestStatus.FAILED)
        skipped = sum(1 for r in self.results if r.status == TestStatus.SKIPPED)
        errors = sum(1 for r in self.results if r.status == TestStatus.ERROR)

        total = len(self.results)
        total_time = sum(r.duration_ms for r in self.results)

        print(f"  Passed:  {passed}/{total}")
        print(f"  Failed:  {failed}/{total}")
        print(f"  Skipped: {skipped}/{total}")
        print(f"  Errors:  {errors}/{total}")
        print(f"  Time:    {total_time:.0f}ms")

        if failed > 0 or errors > 0:
            print("\n  \033[31mStatus: FAILED\033[0m")

            print("\n  Failed tests:")
            for r in self.results:
                if r.status in (TestStatus.FAILED, TestStatus.ERROR):
                    print(f"    - {r.name}: {r.message}")
        else:
            print("\n  \033[32mStatus: PASSED\033[0m")


def list_tests(test_dir: Path) -> None:
    """List available tests."""
    print("Available tests:")
    print("-" * 40)

    for yaml_file in sorted(test_dir.glob("*.yaml")):
        with open(yaml_file) as f:
            data = yaml.safe_load(f)

        category = data.get("category", yaml_file.stem)
        description = data.get("description", "")
        tests = data.get("tests", [])

        print(f"\n[{category}] {description}")
        for test in tests:
            print(f"  - {test.get('name')}: {test.get('description', '')}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="MCP Server Validation Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--url",
        type=str,
        help="Server URL (overrides config)",
    )
    parser.add_argument(
        "--transport",
        choices=["streamable_http", "sse", "stdio"],
        help="Transport protocol (overrides config)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.yaml",
        help="Path to config file",
    )
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        help="Test category to run (can be repeated)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failure",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available tests",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    return parser.parse_args()


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Determine test directory
    test_dir = Path(__file__).parent / "test-cases"

    # List tests if requested
    if args.list:
        list_tests(test_dir)
        return 0

    # Load config
    if args.config.exists():
        config = ValidationConfig.from_yaml(args.config)
    else:
        config = ValidationConfig()

    # Apply CLI overrides
    if args.url:
        config.url = args.url
    if args.transport:
        config.transport = args.transport
    if args.verbose:
        config.verbose = True
    if args.fail_fast:
        config.fail_fast = True
    if args.categories:
        config.categories = args.categories

    # Run validation
    client = MCPValidationClient(config)
    results = await client.run_all_tests(test_dir)

    # Exit code based on results
    failed = sum(
        1 for r in results if r.status in (TestStatus.FAILED, TestStatus.ERROR)
    )
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))