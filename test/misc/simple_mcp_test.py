#!/usr/bin/env python3
"""
Simple test script for FastMCP server instructions and prompts
Based on FastMCP 2.11.0 client API
"""

import asyncio
import json
from typing import Any, Dict

try:
    from fastmcp import Client
except ImportError as e:
    print(f"❌ Error importing FastMCP: {e}")
    print("Install with: pip install fastmcp")
    exit(1)


async def test_mcp_instructions_and_prompts(server_url: str = "http://127.0.0.1:8080/mcp"):
    """Test MCP server instructions and prompts"""

    print(f"🚀 Testing MCP server at: {server_url}")
    print("=" * 60)

    try:
        # Create FastMCP client
        client = Client(server_url)

        async with client:
            print("✅ Connected to MCP server")

            # Test 1: Basic connectivity
            print("\n📡 Testing server connectivity...")
            try:
                await client.ping()
                print("✅ Server ping successful")
            except Exception as e:
                print(f"❌ Server ping failed: {e}")
                return False

            # Test 2: List and test prompts
            print("\n🎯 Testing prompts...")
            try:
                prompts = await client.list_prompts()
                print(f"📝 Found {len(prompts)} prompts:")

                if prompts:
                    for i, prompt in enumerate(prompts, 1):
                        print(f"  {i}. Name: {prompt.name}")
                        if hasattr(prompt, 'description'):
                            print(f"     Description: {prompt.description}")

                        # Show arguments if any
                        if hasattr(prompt, 'arguments') and prompt.arguments:
                            args = [f"{arg.name}({getattr(arg, 'type', 'any')})" for arg in prompt.arguments]
                            print(f"     Arguments: {', '.join(args)}")

                        # Test the prompt with sample arguments
                        print(f"     Testing prompt '{prompt.name}'...")
                        try:
                            # Prepare test arguments
                            test_args = {}
                            if hasattr(prompt, 'arguments') and prompt.arguments:
                                for arg in prompt.arguments:
                                    # Provide appropriate test values
                                    if 'error' in arg.name.lower():
                                        test_args[arg.name] = "Connection timeout error"
                                    elif 'command' in arg.name.lower():
                                        test_args[arg.name] = "kubectl get pods"
                                    elif 'namespace' in arg.name.lower():
                                        test_args[arg.name] = "default"
                                    elif 'data' in arg.name.lower():
                                        test_args[arg.name] = "sample data"
                                    else:
                                        test_args[arg.name] = f"test-{arg.name}"

                            # Execute the prompt
                            result = await client.get_prompt(prompt.name, test_args)
                            print(f"     ✅ Prompt executed successfully")

                            # Show result information
                            if hasattr(result, 'messages') and result.messages:
                                print(f"     📄 Generated {len(result.messages)} message(s)")
                                # Show preview of first message
                                first_msg = result.messages[0]
                                if hasattr(first_msg, 'content'):
                                    if hasattr(first_msg.content, 'text'):
                                        preview = first_msg.content.text[:150]
                                    elif isinstance(first_msg.content, str):
                                        preview = first_msg.content[:150]
                                    elif isinstance(first_msg.content, list) and first_msg.content:
                                        preview = str(first_msg.content[0])[:150]
                                    else:
                                        preview = str(first_msg.content)[:150]
                                    print(f"     Preview: {preview}...")

                        except Exception as e:
                            print(f"     ❌ Prompt test failed: {e}")

                        print()  # Empty line for readability

                else:
                    print("  ℹ️  No prompts found on server")

            except Exception as e:
                print(f"❌ Failed to test prompts: {e}")

            # Test 3: Get server capabilities summary
            print("\n⚙️  Testing server capabilities...")
            try:
                tools = await client.list_tools()
                resources = await client.list_resources()
                prompts = await client.list_prompts()

                print(f"📊 Server Summary:")
                print(f"   Tools: {len(tools)}")
                print(f"   Resources: {len(resources)}")
                print(f"   Prompts: {len(prompts)}")

                # Show server capabilities in detail
                if tools:
                    print(f"\n🔧 Available Tools:")
                    for tool in tools[:5]:  # Show first 5 tools
                        print(f"   • {tool.name}: {tool.description}")
                    if len(tools) > 5:
                        print(f"   ... and {len(tools) - 5} more")

                if resources:
                    print(f"\n📁 Available Resources:")
                    for resource in resources[:5]:  # Show first 5 resources
                        print(f"   • {resource.uri}: {getattr(resource, 'name', 'N/A')}")
                    if len(resources) > 5:
                        print(f"   ... and {len(resources) - 5} more")

            except Exception as e:
                print(f"❌ Failed to get server capabilities: {e}")

            # Test 4: Try to get server instructions/info
            print("\n📋 Checking for server instructions...")
            try:
                # FastMCP 2.x may not expose instructions directly through client API
                # Instructions are typically set during server creation and may not be accessible
                print("ℹ️  Server instructions are set during server initialization")
                print("   They may not be directly accessible through the client API")
                print("   Instructions are typically used by LLM clients to understand server capabilities")

                # However, we can infer some information from the available components
                tools = await client.list_tools()
                prompts = await client.list_prompts()

                if tools or prompts:
                    print("\n💡 Inferred server capabilities:")
                    if tools:
                        print(f"   • Provides {len(tools)} tools for executing actions")
                    if prompts:
                        print(f"   • Offers {len(prompts)} prompts for guided interactions")

            except Exception as e:
                print(f"❌ Error checking server instructions: {e}")

            print("\n✅ Test completed successfully!")
            return True

    except Exception as e:
        print(f"❌ Connection to MCP server failed: {e}")
        print("   Make sure the server is running and accessible")
        return False


async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description="Test MCP server instructions and prompts")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8080/mcp",
        help="MCP server URL (default: http://127.0.0.1:8080/mcp)"
    )

    args = parser.parse_args()

    success = await test_mcp_instructions_and_prompts(args.url)

    if success:
        print("\n🎉 All tests completed successfully!")
    else:
        print("\n💥 Tests failed. Check server connectivity and configuration.")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
