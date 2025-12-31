#!/usr/bin/env python3
"""
MCP Server Validation Client

Validates MCP server compatibility from an external client perspective.
Uses langchain_mcp_adapters to simulate how ai-agent will interact with the server.

Usage:
    # Test against default config (config.yaml)
    python validation_client.py

    # Test against custom URL
    python validation_client.py --url http://localhost:8080/mcp

    # Test specific capabilities
    python validation_client.py --test tools
    python validation_client.py --test all

    # Verbose output
    python validation_client.py -v
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

# Will be used when server has features to test
# from langchain_mcp_adapters.client import MultiServerMCPClient


class ValidationStatus(Enum):
    """Status of validation check."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass
class ValidationResult:
    """Result of a validation test."""

    name: str
    status: ValidationStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationConfig:
    """Configuration for validation client."""

    url: str = "http://127.0.0.1:8765/mcp"
    transport: str = "streamable_http"
    timeout: int = 30
    verbose: bool = False
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
            expected_tools=tests.get("expected_tools", []),
        )


class MCPValidationClient:
    """
    Validation client for testing MCP server compatibility.

    Uses langchain_mcp_adapters to connect to the server and validate
    that it works correctly from a LangChain client perspective.
    """

    def __init__(self, config: ValidationConfig):
        self.config = config
        self.results: list[ValidationResult] = []
        self._client = None

    async def connect(self) -> bool:
        """
        Connect to the MCP server.

        Returns:
            True if connection successful, False otherwise.
        """
        # TODO: Implement when server has features to test
        # self._client = MultiServerMCPClient({
        #     "server": {
        #         "url": self.config.url,
        #         "transport": self.config.transport,
        #     }
        # })
        self._log(f"Would connect to: {self.config.url}")
        self._log(f"Transport: {self.config.transport}")
        return True

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        self._client = None

    def _log(self, message: str) -> None:
        """Log message if verbose mode enabled."""
        if self.config.verbose:
            print(f"  [DEBUG] {message}")

    def _add_result(self, result: ValidationResult) -> None:
        """Add a validation result."""
        self.results.append(result)
        status_icon = {
            ValidationStatus.PASSED: "✓",
            ValidationStatus.FAILED: "✗",
            ValidationStatus.SKIPPED: "○",
            ValidationStatus.NOT_IMPLEMENTED: "·",
        }
        icon = status_icon.get(result.status, "?")
        print(f"  [{icon}] {result.name}: {result.message}")

    # =========================================================================
    # Validation Tests (Skeletons)
    # =========================================================================

    async def validate_connection(self) -> ValidationResult:
        """Validate basic connection to server."""
        # TODO: Implement actual connection test
        return ValidationResult(
            name="Connection",
            status=ValidationStatus.NOT_IMPLEMENTED,
            message="Connection validation not yet implemented",
        )

    async def validate_tools_list(self) -> ValidationResult:
        """Validate tools/list capability."""
        # TODO: Implement when server has tools
        return ValidationResult(
            name="Tools List",
            status=ValidationStatus.NOT_IMPLEMENTED,
            message="Tools list validation not yet implemented",
        )

    async def validate_tool_execution(self, tool_name: str) -> ValidationResult:
        """Validate tool execution capability."""
        # TODO: Implement when server has executable tools
        return ValidationResult(
            name=f"Tool Execution ({tool_name})",
            status=ValidationStatus.NOT_IMPLEMENTED,
            message="Tool execution validation not yet implemented",
        )

    async def validate_prompts(self) -> ValidationResult:
        """Validate prompts/list capability."""
        # TODO: Implement when server has prompts
        return ValidationResult(
            name="Prompts",
            status=ValidationStatus.NOT_IMPLEMENTED,
            message="Prompts validation not yet implemented",
        )

    async def validate_resources(self) -> ValidationResult:
        """Validate resources capability."""
        # TODO: Implement when server has resources
        return ValidationResult(
            name="Resources",
            status=ValidationStatus.NOT_IMPLEMENTED,
            message="Resources validation not yet implemented",
        )

    # =========================================================================
    # Main Validation Runner
    # =========================================================================

    async def run_all_validations(self) -> list[ValidationResult]:
        """Run all validation tests."""
        print("\nMCP Server Validation")
        print("=" * 50)
        print(f"Server: {self.config.url}")
        print(f"Transport: {self.config.transport}")
        print("=" * 50)

        # Connect
        print("\n[1] Connection")
        connected = await self.connect()
        if not connected:
            self._add_result(
                ValidationResult(
                    name="Connection",
                    status=ValidationStatus.FAILED,
                    message="Failed to connect to server",
                )
            )
            return self.results

        self._add_result(await self.validate_connection())

        # Tools
        print("\n[2] Tools")
        self._add_result(await self.validate_tools_list())

        for tool_name in self.config.expected_tools:
            self._add_result(await self.validate_tool_execution(tool_name))

        # Prompts
        print("\n[3] Prompts")
        self._add_result(await self.validate_prompts())

        # Resources
        print("\n[4] Resources")
        self._add_result(await self.validate_resources())

        # Disconnect
        await self.disconnect()

        # Summary
        self._print_summary()

        return self.results

    def _print_summary(self) -> None:
        """Print validation summary."""
        print("\n" + "=" * 50)
        print("Summary")
        print("=" * 50)

        passed = sum(1 for r in self.results if r.status == ValidationStatus.PASSED)
        failed = sum(1 for r in self.results if r.status == ValidationStatus.FAILED)
        skipped = sum(1 for r in self.results if r.status == ValidationStatus.SKIPPED)
        not_impl = sum(
            1 for r in self.results if r.status == ValidationStatus.NOT_IMPLEMENTED
        )

        total = len(self.results)
        print(f"  Passed:          {passed}/{total}")
        print(f"  Failed:          {failed}/{total}")
        print(f"  Skipped:         {skipped}/{total}")
        print(f"  Not Implemented: {not_impl}/{total}")

        if failed > 0:
            print("\n  Status: VALIDATION FAILED")
        elif not_impl == total:
            print("\n  Status: NOT YET IMPLEMENTED (skeleton only)")
        else:
            print("\n  Status: VALIDATION PASSED")


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
        "--test",
        choices=["all", "connection", "tools", "prompts", "resources"],
        default="all",
        help="Which tests to run",
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

    # Run validation
    client = MCPValidationClient(config)
    results = await client.run_all_validations()

    # Exit code based on results
    failed = sum(1 for r in results if r.status == ValidationStatus.FAILED)
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
