#!/usr/bin/env python3
"""
Simple test script for streamable-http MCP client connection
Tests all available tools with version and simple commands
"""

import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient

# Global configuration for tools
TOOLS_CONFIG = {
    "kubectl": {
        "check_cmd": "kubectl version --client",
        "help_flag": "--help",
        "description": "Kubernetes command-line tool",
        "example": "kubectl get pods --all-namespaces"
    },
    "helm": {
        "check_cmd": "helm version",
        "help_flag": "--help",
        "description": "Kubernetes package manager",
        "example": "helm list --all-namespaces"
    },
    "argocd": {
        "check_cmd": "argocd version --client",
        "help_flag": "--help",
        "description": "GitOps continuous delivery tool for Kubernetes",
        "example": "argocd app list"
    }
}


async def test_kubectl_get_namespaces(mcp_client, tools):
    """Test kubectl get namespaces command"""

    print("\n🧪 Testing kubectl get namespaces command...")

    # Find the execute_kubectl tool
    kubectl_tool = None
    for tool in tools:
        if tool.name == "execute_kubectl":
            kubectl_tool = tool
            break

    if kubectl_tool:
        try:
            print("✅ Found execute_kubectl tool, testing get namespaces command...")
            # Use the tool directly
            result = await kubectl_tool.ainvoke({"command": "kubectl get namespaces"})

            if result:
                print("✅ kubectl get namespaces command executed successfully!")
                print(f"Output: {str(result)[:500]}...")

                # Check if we got namespace information
                if "default" in str(result) or "kube-system" in str(result):
                    print("✅ Namespace list retrieved successfully!")
                    return True
                else:
                    print("⚠️  No standard namespaces found in output")
                    return False
            else:
                print("❌ No output from kubectl get namespaces command")
                return False
        except Exception as e:
            print(f"❌ kubectl get namespaces test failed: {str(e)}")
            return False
    else:
        print("❌ execute_kubectl tool not found")
        return False


async def test_streamable_http_connection():
    """Test the streamable-http connection to the k8s-mcp-server"""

    # Configure the client
    k8s_mcp_config = {
        "url": "http://127.0.0.1:8080/mcp",
        "transport": "streamable_http"
    }

    # Track test results
    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    test_results = []

    try:
        # Initialize the client
        print("🔄 Initializing MCP client...")
        mcp_client = MultiServerMCPClient({"k8s": k8s_mcp_config})

        # Test connection by listing tools
        print("🔍 Testing connection by listing available tools...")
        tools = await mcp_client.get_tools()

        print(f"✅ Connection successful! Found {len(tools)} tools:")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description}")

        # Test each tool with version and simple commands
        for tool in tools:
            print(f"\n🔧 Testing tool: {tool.name}")
            tool_passed = 0
            tool_failed = 0

            try:
                if tool.name == "execute_kubectl":
                    config = TOOLS_CONFIG["kubectl"]
                    # Test 1: Version command
                    print(f"  📝 Test 1: {config['check_cmd']}")
                    result = await tool.ainvoke({"command": config["check_cmd"]})
                    print(f"  ✅ Version result: {str(result)[:200]}...")
                    tool_passed += 1

                    # Test 2: Example command
                    print(f"  📝 Test 2: {config['example']}")
                    result = await tool.ainvoke({"command": config["example"]})
                    print(f"  ✅ Example result: {str(result)[:200]}...")
                    tool_passed += 1

                elif tool.name == "execute_helm":
                    config = TOOLS_CONFIG["helm"]
                    # Test 1: Version command
                    print(f"  📝 Test 1: {config['check_cmd']}")
                    result = await tool.ainvoke({"command": config["check_cmd"]})
                    print(f"  ✅ Version result: {str(result)[:200]}...")
                    tool_passed += 1

                    # Test 2: Example command
                    print(f"  📝 Test 2: {config['example']}")
                    result = await tool.ainvoke({"command": config["example"]})
                    print(f"  ✅ Example result: {str(result)[:200]}...")
                    tool_passed += 1

                elif tool.name == "execute_argocd":
                    config = TOOLS_CONFIG["argocd"]
                    # Test 1: Version command
                    print(f"  📝 Test 1: {config['check_cmd']}")
                    result = await tool.ainvoke({"command": config["check_cmd"]})
                    print(f"  ✅ Version result: {str(result)[:200]}...")
                    tool_passed += 1

                    # Test 2: Example command
                    print(f"  📝 Test 2: {config['example']}")
                    result = await tool.ainvoke({"command": config["example"]})
                    print(f"  ✅ Example result: {str(result)[:200]}...")
                    tool_passed += 1

                elif tool.name == "describe_kubectl":
                    config = TOOLS_CONFIG["kubectl"]
                    # Test 1: General help
                    print(f"  📝 Test 1: kubectl help")
                    result = await tool.ainvoke({"command": None})
                    print(f"  ✅ Help result: {str(result)[:200]}...")
                    tool_passed += 1

                    # Test 2: Specific command help
                    print(f"  📝 Test 2: kubectl get help")
                    result = await tool.ainvoke({"command": "get"})
                    print(f"  ✅ Get help result: {str(result)[:200]}...")
                    tool_passed += 1

                elif tool.name == "describe_helm":
                    config = TOOLS_CONFIG["helm"]
                    # Test 1: General help
                    print(f"  📝 Test 1: helm help")
                    result = await tool.ainvoke({"command": None})
                    print(f"  ✅ Help result: {str(result)[:200]}...")
                    tool_passed += 1

                    # Test 2: Specific command help
                    print(f"  📝 Test 2: helm install help")
                    result = await tool.ainvoke({"command": "install"})
                    print(f"  ✅ Install help result: {str(result)[:200]}...")
                    tool_passed += 1

                elif tool.name == "describe_argocd":
                    config = TOOLS_CONFIG["argocd"]
                    # Test 1: General help
                    print(f"  📝 Test 1: argocd help")
                    result = await tool.ainvoke({"command": None})
                    print(f"  ✅ Help result: {str(result)[:200]}...")
                    tool_passed += 1

                    # Test 2: Specific command help
                    print(f"  📝 Test 2: argocd app help")
                    result = await tool.ainvoke({"command": "app"})
                    print(f"  ✅ App help result: {str(result)[:200]}...")
                    tool_passed += 1

                else:
                    # Unknown tool - try basic invocation
                    print(f"  📝 Unknown tool, trying basic invocation")
                    result = await tool.ainvoke({})
                    print(f"  ✅ Basic result: {str(result)[:200]}...")
                    tool_passed += 1

            except Exception as e:
                print(f"  ❌ Tool {tool.name} failed: {str(e)}")
                print(f"     This appears to be a server-side issue with the {tool.name} implementation")
                tool_failed = 2  # Each tool should have 2 tests

            # Record results for this tool
            test_results.append({
                "tool": tool.name,
                "passed": tool_passed,
                "failed": tool_failed,
                "total": 2  # Each tool always has 2 tests
            })

            total_tests += 2
            passed_tests += tool_passed
            failed_tests += tool_failed

        # Test kubectl get namespaces command (additional test)
        namespace_test_passed = await test_kubectl_get_namespaces(mcp_client, tools)
        total_tests += 1
        if namespace_test_passed:
            passed_tests += 1
        else:
            failed_tests += 1

    except Exception as e:
        print(f"❌ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Print comprehensive test summary
    print(f"\n{'=' * 60}")
    print(f"📊 TEST SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total Tests: {total_tests}")
    print(f"✅ Passed: {passed_tests}")
    print(f"❌ Failed: {failed_tests}")
    print(f"Success Rate: {(passed_tests / total_tests * 100):.1f}%" if total_tests > 0 else "0%")

    print(f"\n📋 TOOL-BY-TOOL BREAKDOWN:")
    for result in test_results:
        if result["failed"] == 0:
            status_icon = "✅"
        elif result["passed"] == 0:
            status_icon = "❌"
        else:
            status_icon = "⚠️"
        print(f"{status_icon} {result['tool']}: {result['passed']}/{result['total']} tests passed")

    # Additional namespace test
    namespace_status = "✅" if namespace_test_passed else "❌"
    print(f"{namespace_status} kubectl_get_namespaces: {'1/1' if namespace_test_passed else '0/1'} tests passed")

    # Return True only if ALL tests passed
    return failed_tests == 0


if __name__ == "__main__":
    print("🚀 Testing streamable-http MCP client connection...")
    success = asyncio.run(test_streamable_http_connection())

    if success:
        print("\n🎉 All tests passed! Your streamable-http configuration is working correctly.")
    else:
        print("\n💥 Some tests failed. Check the summary above for details.")
        print("   Note: Failed tests may indicate server-side implementation issues.")

