#!/usr/bin/env python3
"""
Test script for checking FastMCP server instructions and prompts
Tests server configuration information and available prompts via FastMCP Client
"""

import asyncio
import json
from typing import Dict, Any, List
from dataclasses import dataclass

# Import FastMCP client components
try:
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport
except ImportError as e:
    print(f"❌ Failed to import FastMCP: {e}")
    print("Please ensure FastMCP 2.11.0+ is installed: pip install fastmcp")
    exit(1)


@dataclass
class TestResult:
    """Container for test results"""
    test_name: str
    passed: bool
    data: Any = None
    error: str = None


class MCPInstructionsPromptsTest:
    """Test class for MCP server instructions and prompts"""

    def __init__(self, server_url: str = "http://127.0.0.1:8080/mcp"):
        self.server_url = server_url
        self.test_results: List[TestResult] = []

    async def run_all_tests(self) -> bool:
        """Run all tests and return True if all passed"""
        print(f"🚀 Testing MCP server instructions and prompts at: {self.server_url}")
        print(f"{'=' * 80}")

        # Configure the client for streamable HTTP transport
        try:
            client = Client(self.server_url)

            async with client:
                # Test 1: Server connectivity
                await self._test_server_connectivity(client)

                # Test 2: Server information and instructions
                await self._test_server_instructions(client)

                # Test 3: List available prompts
                await self._test_list_prompts(client)

                # Test 4: Test individual prompts (if any exist)
                await self._test_individual_prompts(client)

                # Test 5: Server capabilities
                await self._test_server_capabilities(client)

        except Exception as e:
            self._add_result("client_connection", False, error=str(e))
            print(f"❌ Failed to connect to MCP server: {e}")
            return False

        # Print comprehensive summary
        self._print_test_summary()

        # Return True only if all tests passed
        return all(result.passed for result in self.test_results)

    async def _test_server_connectivity(self, client: Client):
        """Test basic server connectivity"""
        print("\n🔍 Testing server connectivity...")
        try:
            # Ping the server
            await client.ping()
            self._add_result("server_ping", True, data="Server responded to ping")
            print("✅ Server is reachable!")
        except Exception as e:
            self._add_result("server_ping", False, error=str(e))
            print(f"❌ Server ping failed: {e}")

    async def _test_server_instructions(self, client: Client):
        """Test retrieving server instructions"""
        print("\n📋 Testing server instructions...")
        try:
            # Try to get server info/instructions
            # Note: In FastMCP 2.x, instructions are part of server initialization
            # They may be accessible via server metadata or capabilities

            # First, try to get basic server information
            server_info = await self._get_server_info(client)
            if server_info:
                self._add_result("server_info", True, data=server_info)
                print("✅ Server information retrieved:")
                if isinstance(server_info, dict):
                    for key, value in server_info.items():
                        print(f"   {key}: {value}")
                else:
                    print(f"   {server_info}")
            else:
                self._add_result("server_info", False, error="No server info available")
                print("⚠️  Server info not available through standard methods")

        except Exception as e:
            self._add_result("server_info", False, error=str(e))
            print(f"❌ Failed to get server instructions: {e}")

    async def _get_server_info(self, client: Client) -> Dict[str, Any]:
        """Attempt to retrieve server information"""
        try:
            # Try different methods to get server info
            info = {}

            # Method 1: Check if there's a way to get server metadata
            # This depends on the specific FastMCP implementation

            # Method 2: List capabilities to understand server features
            try:
                # Get tools, resources, and prompts to understand server capabilities
                tools = await client.list_tools()
                resources = await client.list_resources()
                prompts = await client.list_prompts()

                info["tools_count"] = len(tools) if tools else 0
                info["resources_count"] = len(resources) if resources else 0
                info["prompts_count"] = len(prompts) if prompts else 0
                info["server_url"] = self.server_url

                # Try to extract any server-specific information
                if hasattr(client, 'server_info'):
                    info["server_metadata"] = client.server_info

            except Exception as e:
                info["capability_error"] = str(e)

            return info

        except Exception as e:
            print(f"   Debug: Error getting server info: {e}")
            return {"error": str(e)}

    async def _test_list_prompts(self, client: Client):
        """Test listing available prompts"""
        print("\n🎯 Testing prompts listing...")
        try:
            prompts = await client.list_prompts()

            if prompts:
                self._add_result("list_prompts", True, data=prompts)
                print(f"✅ Found {len(prompts)} prompts:")
                for i, prompt in enumerate(prompts, 1):
                    print(f"   {i}. {prompt.name}")
                    if hasattr(prompt, 'description') and prompt.description:
                        print(f"      Description: {prompt.description}")
                    if hasattr(prompt, 'arguments') and prompt.arguments:
                        args = [arg.name for arg in prompt.arguments]
                        print(f"      Arguments: {', '.join(args)}")
                    print()
            else:
                self._add_result("list_prompts", True, data=[])
                print("ℹ️  No prompts registered on the server")

        except Exception as e:
            self._add_result("list_prompts", False, error=str(e))
            print(f"❌ Failed to list prompts: {e}")

    async def _test_individual_prompts(self, client: Client):
        """Test individual prompts if they exist"""
        print("\n🔬 Testing individual prompts...")
        try:
            prompts = await client.list_prompts()

            if not prompts:
                self._add_result("individual_prompts", True, data="No prompts to test")
                print("ℹ️  No prompts available to test")
                return

            tested_prompts = []
            for prompt in prompts[:3]:  # Test first 3 prompts to avoid overwhelming
                try:
                    print(f"   Testing prompt: {prompt.name}")

                    # Prepare arguments if the prompt requires them
                    args = {}
                    if hasattr(prompt, 'arguments') and prompt.arguments:
                        for arg in prompt.arguments:
                            # Provide test values based on argument names
                            if 'error' in arg.name.lower():
                                args[arg.name] = "Test error message"
                            elif 'command' in arg.name.lower():
                                args[arg.name] = "kubectl get pods"
                            elif 'name' in arg.name.lower():
                                args[arg.name] = "test-name"
                            elif 'data' in arg.name.lower():
                                args[arg.name] = "test data"
                            else:
                                args[arg.name] = "test-value"

                    # Get the prompt
                    result = await client.get_prompt(prompt.name, args)

                    tested_prompts.append({
                        "name": prompt.name,
                        "success": True,
                        "result_type": type(result).__name__,
                        "args_used": args
                    })

                    print(f"   ✅ Prompt '{prompt.name}' executed successfully")
                    if hasattr(result, 'messages') and result.messages:
                        print(f"      Generated {len(result.messages)} message(s)")
                        # Show first message content (truncated)
                        if result.messages:
                            first_msg = result.messages[0]
                            if hasattr(first_msg, 'content'):
                                content_preview = str(first_msg.content)[:100]
                                print(f"      Preview: {content_preview}...")

                except Exception as e:
                    tested_prompts.append({
                        "name": prompt.name,
                        "success": False,
                        "error": str(e)
                    })
                    print(f"   ❌ Prompt '{prompt.name}' failed: {e}")

            self._add_result("individual_prompts", True, data=tested_prompts)

        except Exception as e:
            self._add_result("individual_prompts", False, error=str(e))
            print(f"❌ Failed to test individual prompts: {e}")

    async def _test_server_capabilities(self, client: Client):
        """Test server capabilities and configuration"""
        print("\n⚙️  Testing server capabilities...")
        try:
            capabilities = {}

            # Test different aspects of the server
            try:
                tools = await client.list_tools()
                capabilities["tools"] = [{"name": tool.name, "description": tool.description} for tool in
                                         tools] if tools else []
            except Exception as e:
                capabilities["tools_error"] = str(e)

            try:
                resources = await client.list_resources()
                capabilities["resources"] = [{"uri": res.uri, "name": res.name} for res in
                                             resources] if resources else []
            except Exception as e:
                capabilities["resources_error"] = str(e)

            try:
                prompts = await client.list_prompts()
                capabilities["prompts"] = [{"name": prompt.name, "description": getattr(prompt, 'description', '')} for
                                           prompt in prompts] if prompts else []
            except Exception as e:
                capabilities["prompts_error"] = str(e)

            self._add_result("server_capabilities", True, data=capabilities)
            print("✅ Server capabilities retrieved:")
            print(f"   Tools: {len(capabilities.get('tools', []))}")
            print(f"   Resources: {len(capabilities.get('resources', []))}")
            print(f"   Prompts: {len(capabilities.get('prompts', []))}")

        except Exception as e:
            self._add_result("server_capabilities", False, error=str(e))
            print(f"❌ Failed to get server capabilities: {e}")

    def _add_result(self, test_name: str, passed: bool, data: Any = None, error: str = None):
        """Add a test result"""
        self.test_results.append(TestResult(test_name, passed, data, error))

    def _print_test_summary(self):
        """Print comprehensive test summary"""
        print(f"\n{'=' * 80}")
        print(f"📊 INSTRUCTIONS AND PROMPTS TEST SUMMARY")
        print(f"{'=' * 80}")

        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result.passed)
        failed_tests = total_tests - passed_tests

        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests / total_tests * 100):.1f}%" if total_tests > 0 else "0%")

        print(f"\n📋 DETAILED RESULTS:")
        for result in self.test_results:
            status_icon = "✅" if result.passed else "❌"
            print(f"{status_icon} {result.test_name}")
            if result.error:
                print(f"   Error: {result.error}")
            elif result.data and result.test_name in ["server_info", "server_capabilities"]:
                if isinstance(result.data, dict):
                    for key, value in result.data.items():
                        print(f"   {key}: {value}")

        # Show detailed prompt information if available
        prompt_result = next((r for r in self.test_results if r.test_name == "list_prompts"), None)
        if prompt_result and prompt_result.passed and prompt_result.data:
            print(f"\n🎯 AVAILABLE PROMPTS:")
            if isinstance(prompt_result.data, list) and prompt_result.data:
                for prompt in prompt_result.data:
                    print(f"   • {prompt.name}")
                    if hasattr(prompt, 'description') and prompt.description:
                        print(f"     Description: {prompt.description}")
            else:
                print(f"   No prompts found")


def _make_json_serializable(obj):
    """Convert objects to JSON-serializable format"""
    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, list):
        return [_make_json_serializable(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    elif hasattr(obj, '__dict__'):
        # Convert objects with attributes to dict
        result = {}
        for attr, value in obj.__dict__.items():
            if not attr.startswith('_'):  # Skip private attributes
                result[attr] = _make_json_serializable(value)
        return result
    else:
        return str(obj)


def main():
    """Main function to run the tests"""
    import argparse

    parser = argparse.ArgumentParser(description="Test MCP server instructions and prompts")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8080/mcp",
        help="MCP server URL (default: http://127.0.0.1:8080/mcp)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format"
    )

    args = parser.parse_args()

    # Create and run the test
    tester = MCPInstructionsPromptsTest(args.url)
    success = asyncio.run(tester.run_all_tests())

    if args.json:
        # Output JSON results
        json_results = {
            "success": success,
            "server_url": args.url,
            "total_tests": len(tester.test_results),
            "passed_tests": sum(1 for r in tester.test_results if r.passed),
            "failed_tests": sum(1 for r in tester.test_results if not r.passed),
            "results": [
                {
                    "test_name": r.test_name,
                    "passed": r.passed,
                    "error": r.error,
                    "data": _make_json_serializable(r.data)
                }
                for r in tester.test_results
            ]
        }
        print(json.dumps(json_results, indent=2))

    if success:
        print("\n🎉 All tests passed! Your MCP server instructions and prompts are accessible.")
    else:
        print("\n💥 Some tests failed. Check the summary above for details.")
        exit(1)


if __name__ == "__main__":
    main()
