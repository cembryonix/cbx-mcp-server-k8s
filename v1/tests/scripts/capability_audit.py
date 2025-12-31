#!/usr/bin/env python3
"""
Ad Hoc MCP Server Functional Test
=================================

Simple, direct testing to see what MCP features are implemented and working.
No complex framework - just straightforward capability verification.

Usage:
    python adhoc_mcp_test.py --server-url http://127.0.0.1:8080/mcp
    python adhoc_mcp_test.py --config custom_server_config.json
"""

import asyncio
import json
import argparse
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

from langchain_mcp_adapters.client import MultiServerMCPClient


class CapabilityStatus(Enum):
    """Status of MCP capability check"""
    IMPLEMENTED = "✅ Implemented"
    NOT_IMPLEMENTED = "❌ Not Implemented"
    PARTIALLY_IMPLEMENTED = "⚠️  Partially Implemented"
    ERROR = "🔥 Error"
    UNKNOWN = "❓ Unknown"


@dataclass
class CapabilityResult:
    """Result of testing an MCP capability"""
    name: str
    status: CapabilityStatus
    details: str
    data: Optional[Any] = None
    error: Optional[str] = None


class MCPServerCapabilityTester:
    """
    Ad hoc tester for MCP server capabilities
    Tests what's actually implemented vs what should be implemented
    """

    def __init__(self, server_config: Dict[str, Any]):
        self.server_config = server_config
        self.client: Optional[MultiServerMCPClient] = None
        self.results: List[CapabilityResult] = []

        # Tool configurations for testing (your current TOOLS_CONFIG)
        self.TOOLS_CONFIG = {
            "kubectl": {
                "execute_tool": "execute_kubectl",
                "describe_tool": "describe_kubectl",
                "version_cmd": "kubectl version --client",
                "example_cmd": "kubectl get namespaces",
                "help_cmd": None
            },
            "helm": {
                "execute_tool": "execute_helm",
                "describe_tool": "describe_helm",
                "version_cmd": "helm version",
                "example_cmd": "helm list --all-namespaces",
                "help_cmd": None
            },
            "argocd": {
                "execute_tool": "execute_argocd",
                "describe_tool": "describe_argocd",
                "version_cmd": "argocd version --client",
                "example_cmd": "argocd app list",
                "help_cmd": None
            }
        }

    async def connect(self) -> bool:
        """Connect to MCP server"""
        try:
            print(f"🔗 Connecting to MCP server: {self.server_config}")
            self.client = MultiServerMCPClient({"test_server": self.server_config})
            return True
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False

    async def disconnect(self):
        """Disconnect from server"""
        if self.client:
            self.client = None

    # =========================================================================
    # CAPABILITY TESTS
    # =========================================================================

    async def test_basic_connection(self) -> CapabilityResult:
        """Test 1: Basic server connection and responsiveness"""
        try:
            # Try to get tools list as connectivity test
            tools = await self.client.get_tools()
            return CapabilityResult(
                name="Basic Connection",
                status=CapabilityStatus.IMPLEMENTED,
                details=f"Server responsive, found {len(tools)} tools",
                data={"tool_count": len(tools)}
            )
        except Exception as e:
            return CapabilityResult(
                name="Basic Connection",
                status=CapabilityStatus.ERROR,
                details="Server not responding",
                error=str(e)
            )

    async def test_tools_listing(self) -> CapabilityResult:
        """Test 2: Get tools list (MCP core capability)"""
        try:
            tools = await self.client.get_tools()
            tool_names = [tool.name for tool in tools]

            # Check if expected tools are present
            expected_tools = []
            for config in self.TOOLS_CONFIG.values():
                expected_tools.extend([config["execute_tool"], config["describe_tool"]])

            found_tools = [name for name in expected_tools if name in tool_names]
            missing_tools = [name for name in expected_tools if name not in tool_names]

            if len(missing_tools) == 0:
                status = CapabilityStatus.IMPLEMENTED
                details = f"All {len(expected_tools)} expected tools found"
            elif len(found_tools) > 0:
                status = CapabilityStatus.PARTIALLY_IMPLEMENTED
                details = f"Found {len(found_tools)}/{len(expected_tools)} expected tools. Missing: {missing_tools}"
            else:
                status = CapabilityStatus.NOT_IMPLEMENTED
                details = f"No expected tools found. Available: {tool_names}"

            return CapabilityResult(
                name="Tools Listing",
                status=status,
                details=details,
                data={
                    "available_tools": tool_names,
                    "expected_tools": expected_tools,
                    "found_tools": found_tools,
                    "missing_tools": missing_tools
                }
            )

        except Exception as e:
            return CapabilityResult(
                name="Tools Listing",
                status=CapabilityStatus.ERROR,
                details="Failed to get tools list",
                error=str(e)
            )

    async def test_tool_execution(self) -> List[CapabilityResult]:
        """Test 3: Execute each tool from TOOLS_CONFIG"""
        results = []

        try:
            tools = await self.client.get_tools()
            tools_by_name = {tool.name: tool for tool in tools}

            for tool_key, config in self.TOOLS_CONFIG.items():
                # Test execute tool
                execute_tool_name = config["execute_tool"]
                if execute_tool_name in tools_by_name:
                    result = await self._test_single_tool_execution(
                        tools_by_name[execute_tool_name],
                        config["version_cmd"],
                        f"{tool_key} Execute Tool"
                    )
                    results.append(result)
                else:
                    results.append(CapabilityResult(
                        name=f"{tool_key} Execute Tool",
                        status=CapabilityStatus.NOT_IMPLEMENTED,
                        details=f"Tool '{execute_tool_name}' not found"
                    ))

                # Test describe tool
                describe_tool_name = config["describe_tool"]
                if describe_tool_name in tools_by_name:
                    result = await self._test_single_tool_help(
                        tools_by_name[describe_tool_name],
                        config["help_cmd"],
                        f"{tool_key} Describe Tool"
                    )
                    results.append(result)
                else:
                    results.append(CapabilityResult(
                        name=f"{tool_key} Describe Tool",
                        status=CapabilityStatus.NOT_IMPLEMENTED,
                        details=f"Tool '{describe_tool_name}' not found"
                    ))

        except Exception as e:
            results.append(CapabilityResult(
                name="Tool Execution",
                status=CapabilityStatus.ERROR,
                details="Failed to test tool execution",
                error=str(e)
            ))

        return results

    async def _test_single_tool_execution(self, tool, command: str, test_name: str) -> CapabilityResult:
        """Test execution of a single tool"""
        try:
            result = await tool.ainvoke({"command": command})

            if result and str(result).strip():
                return CapabilityResult(
                    name=test_name,
                    status=CapabilityStatus.IMPLEMENTED,
                    details=f"Command executed successfully: '{command}'",
                    data={"output": str(result)[:200] + "..." if len(str(result)) > 200 else str(result)}
                )
            else:
                return CapabilityResult(
                    name=test_name,
                    status=CapabilityStatus.PARTIALLY_IMPLEMENTED,
                    details=f"Tool executed but returned empty result for: '{command}'"
                )

        except Exception as e:
            return CapabilityResult(
                name=test_name,
                status=CapabilityStatus.ERROR,
                details=f"Tool execution failed for: '{command}'",
                error=str(e)
            )

    async def _test_single_tool_help(self, tool, help_cmd: Optional[str], test_name: str) -> CapabilityResult:
        """Test help/describe functionality of a tool"""
        try:
            result = await tool.ainvoke({"command": help_cmd})

            if result and "help" in str(result).lower():
                return CapabilityResult(
                    name=test_name,
                    status=CapabilityStatus.IMPLEMENTED,
                    details="Help functionality working",
                    data={"help_output": str(result)[:200] + "..."}
                )
            else:
                return CapabilityResult(
                    name=test_name,
                    status=CapabilityStatus.PARTIALLY_IMPLEMENTED,
                    details="Help command executed but output unclear"
                )

        except Exception as e:
            return CapabilityResult(
                name=test_name,
                status=CapabilityStatus.ERROR,
                details="Help functionality failed",
                error=str(e)
            )

    async def test_resources_support(self) -> CapabilityResult:
        """Test 4: Check if server supports resources (MCP capability)"""
        try:
            # Try to get resources list
            # Note: This depends on your MCP client library having a get_resources method
            if hasattr(self.client, 'get_resources'):
                resources = await self.client.get_resources()
                return CapabilityResult(
                    name="Resources Support",
                    status=CapabilityStatus.IMPLEMENTED,
                    details=f"Found {len(resources)} resources",
                    data={"resources": [r.name if hasattr(r, 'name') else str(r) for r in resources]}
                )
            else:
                # Try alternative method to detect resources capability
                return CapabilityResult(
                    name="Resources Support",
                    status=CapabilityStatus.UNKNOWN,
                    details="Cannot determine if resources are supported (client limitation)"
                )

        except Exception as e:
            if "not implemented" in str(e).lower() or "not supported" in str(e).lower():
                return CapabilityResult(
                    name="Resources Support",
                    status=CapabilityStatus.NOT_IMPLEMENTED,
                    details="Resources not implemented on server"
                )
            else:
                return CapabilityResult(
                    name="Resources Support",
                    status=CapabilityStatus.ERROR,
                    details="Error checking resources support",
                    error=str(e)
                )

    async def test_prompts_support(self) -> CapabilityResult:
        """Test 5: Check if server supports prompts (MCP capability)"""
        try:
            # Try to get prompts list
            if hasattr(self.client, 'get_prompts'):
                prompts = await self.client.get_prompts()
                return CapabilityResult(
                    name="Prompts Support",
                    status=CapabilityStatus.IMPLEMENTED,
                    details=f"Found {len(prompts)} prompts",
                    data={"prompts": [p.name if hasattr(p, 'name') else str(p) for p in prompts]}
                )
            else:
                return CapabilityResult(
                    name="Prompts Support",
                    status=CapabilityStatus.UNKNOWN,
                    details="Cannot determine if prompts are supported (client limitation)"
                )

        except Exception as e:
            if "not implemented" in str(e).lower() or "not supported" in str(e).lower():
                return CapabilityResult(
                    name="Prompts Support",
                    status=CapabilityStatus.NOT_IMPLEMENTED,
                    details="Prompts not implemented on server"
                )
            else:
                return CapabilityResult(
                    name="Prompts Support",
                    status=CapabilityStatus.ERROR,
                    details="Error checking prompts support",
                    error=str(e)
                )

    async def test_server_sampling_capability(self) -> CapabilityResult:
        """Test 6: Check if server can request sampling from client (advanced MCP)"""
        # This is an advanced MCP feature where server asks client to query LLM
        try:
            # This would require specific implementation to test
            # For now, just check if the capability exists
            return CapabilityResult(
                name="Server Sampling (LLM Elicitation)",
                status=CapabilityStatus.NOT_IMPLEMENTED,
                details="Feature not testable with current client - would need custom implementation"
            )

        except Exception as e:
            return CapabilityResult(
                name="Server Sampling (LLM Elicitation)",
                status=CapabilityStatus.ERROR,
                details="Error checking sampling capability",
                error=str(e)
            )

    async def test_logging_capability(self) -> CapabilityResult:
        """Test 7: Check if server supports logging messages to client"""
        try:
            # This would require testing during tool execution
            # For now, mark as unknown since it requires specific testing
            return CapabilityResult(
                name="Logging Support",
                status=CapabilityStatus.UNKNOWN,
                details="Logging capability requires execution-time testing"
            )

        except Exception as e:
            return CapabilityResult(
                name="Logging Support",
                status=CapabilityStatus.ERROR,
                details="Error checking logging capability",
                error=str(e)
            )

    async def test_progress_reporting(self) -> CapabilityResult:
        """Test 8: Check if server supports progress reporting"""
        try:
            # This would require long-running operations to test properly
            return CapabilityResult(
                name="Progress Reporting",
                status=CapabilityStatus.UNKNOWN,
                details="Progress reporting requires long-running operation testing"
            )

        except Exception as e:
            return CapabilityResult(
                name="Progress Reporting",
                status=CapabilityStatus.ERROR,
                details="Error checking progress reporting",
                error=str(e)
            )

    # =========================================================================
    # TEST EXECUTION
    # =========================================================================

    async def run_all_capability_tests(self) -> List[CapabilityResult]:
        """Run all capability tests and return results"""
        print("🧪 Starting MCP Server Capability Tests")
        print("=" * 60)

        all_results = []

        # Test 1: Basic Connection
        print("Testing basic connection...")
        result = await self.test_basic_connection()
        all_results.append(result)
        self._print_result(result)

        if result.status == CapabilityStatus.ERROR:
            print("❌ Cannot continue tests - server connection failed")
            return all_results

        # Test 2: Tools Listing
        print("\nTesting tools listing...")
        result = await self.test_tools_listing()
        all_results.append(result)
        self._print_result(result)

        # Test 3: Tool Execution
        print("\nTesting tool execution...")
        execution_results = await self.test_tool_execution()
        all_results.extend(execution_results)
        for result in execution_results:
            self._print_result(result)

        # Test 4: Resources Support
        print("\nTesting resources support...")
        result = await self.test_resources_support()
        all_results.append(result)
        self._print_result(result)

        # Test 5: Prompts Support
        print("\nTesting prompts support...")
        result = await self.test_prompts_support()
        all_results.append(result)
        self._print_result(result)

        # Test 6: Server Sampling
        print("\nTesting server sampling capability...")
        result = await self.test_server_sampling_capability()
        all_results.append(result)
        self._print_result(result)

        # Test 7: Logging
        print("\nTesting logging capability...")
        result = await self.test_logging_capability()
        all_results.append(result)
        self._print_result(result)

        # Test 8: Progress Reporting
        print("\nTesting progress reporting...")
        result = await self.test_progress_reporting()
        all_results.append(result)
        self._print_result(result)

        return all_results

    def _print_result(self, result: CapabilityResult):
        """Print a single test result"""
        print(f"  {result.status.value} {result.name}: {result.details}")
        if result.error:
            print(f"    Error: {result.error}")

    def generate_summary_report(self, results: List[CapabilityResult]) -> str:
        """Generate summary report of what's implemented vs not implemented"""

        implemented = [r for r in results if r.status == CapabilityStatus.IMPLEMENTED]
        partially = [r for r in results if r.status == CapabilityStatus.PARTIALLY_IMPLEMENTED]
        not_implemented = [r for r in results if r.status == CapabilityStatus.NOT_IMPLEMENTED]
        errors = [r for r in results if r.status == CapabilityStatus.ERROR]
        unknown = [r for r in results if r.status == CapabilityStatus.UNKNOWN]

        report = []
        report.append("=" * 60)
        report.append("MCP SERVER CAPABILITY SUMMARY")
        report.append("=" * 60)
        report.append("")

        report.append(f"✅ IMPLEMENTED ({len(implemented)}):")
        for r in implemented:
            report.append(f"  • {r.name}")
        report.append("")

        if partially:
            report.append(f"⚠️  PARTIALLY IMPLEMENTED ({len(partially)}):")
            for r in partially:
                report.append(f"  • {r.name}: {r.details}")
            report.append("")

        if not_implemented:
            report.append(f"❌ NOT IMPLEMENTED ({len(not_implemented)}):")
            for r in not_implemented:
                report.append(f"  • {r.name}")
            report.append("")

        if errors:
            report.append(f"🔥 ERRORS ({len(errors)}):")
            for r in errors:
                report.append(f"  • {r.name}: {r.details}")
            report.append("")

        if unknown:
            report.append(f"❓ UNKNOWN/UNTESTABLE ({len(unknown)}):")
            for r in unknown:
                report.append(f"  • {r.name}: {r.details}")
            report.append("")

        # Implementation status
        total_testable = len(implemented) + len(partially) + len(not_implemented) + len(errors)
        if total_testable > 0:
            impl_percentage = (len(implemented) + len(partially) * 0.5) / total_testable * 100
            report.append(f"IMPLEMENTATION STATUS: {impl_percentage:.1f}% complete")

        return "\n".join(report)


# =============================================================================
# MAIN EXECUTION
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Ad hoc MCP server capability testing")
    parser.add_argument("--server-url", default="http://127.0.0.1:8080/mcp",
                        help="MCP server URL")
    parser.add_argument("--transport", default="streamable_http",
                        help="Transport type")
    parser.add_argument("--config", help="JSON config file for server connection")
    parser.add_argument("--output", help="Save results to JSON file")

    args = parser.parse_args()

    # Build server config
    if args.config:
        with open(args.config) as f:
            server_config = json.load(f)
    else:
        server_config = {
            "url": args.server_url,
            "transport": args.transport
        }

    print(f"🚀 MCP Server Ad Hoc Capability Testing")
    print(f"Server: {server_config}")
    print("")

    # Run tests
    tester = MCPServerCapabilityTester(server_config)

    try:
        if await tester.connect():
            results = await tester.run_all_capability_tests()

            # Generate summary
            summary = tester.generate_summary_report(results)
            print("\n" + summary)

            # Save results if requested
            if args.output:
                output_data = {
                    "server_config": server_config,
                    "results": [
                        {
                            "name": r.name,
                            "status": r.status.value,
                            "details": r.details,
                            "data": r.data,
                            "error": r.error
                        }
                        for r in results
                    ],
                    "summary": summary
                }

                with open(args.output, 'w') as f:
                    json.dump(output_data, f, indent=2)
                print(f"\n📄 Results saved to {args.output}")

    finally:
        await tester.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
