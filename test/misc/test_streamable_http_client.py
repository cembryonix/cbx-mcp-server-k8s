#!/usr/bin/env python3
"""
Test script for streamable-http MCP client connection
"""

import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient

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
        print("✅ Found execute_kubectl tool, testing get namespaces command...")
        # Use the tool directly
        result = await kubectl_tool.ainvoke({"command": "kubectl get namespaces"})
        
        if result:
            print("✅ kubectl get namespaces command executed successfully!")
            print(f"Output: {str(result)[:500]}...")
            
            # Check if we got namespace information
            if "default" in str(result) or "kube-system" in str(result):
                print("✅ Namespace list retrieved successfully!")
            else:
                print("⚠️  No standard namespaces found in output")
        else:
            print("❌ No output from kubectl get namespaces command")
    else:
        print("❌ execute_kubectl tool not found")

async def test_streamable_http_connection():
    """Test the streamable-http connection to the k8s-mcp-server"""
    
    # Configure the client
    k8s_mcp_config = {
        "url": "http://127.0.0.1:8080/mcp",
        "transport": "streamable_http"
    }

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
            
        # Test a simple kubectl command
        print("\n🧪 Testing kubectl version command...")
        # Find the execute_kubectl tool
        kubectl_tool = None
        for tool in tools:
            if tool.name == "execute_kubectl":
                kubectl_tool = tool
                break
        
        if kubectl_tool:
            print("✅ Found execute_kubectl tool, testing command...")
            # Use the tool directly
            result = await kubectl_tool.ainvoke({"command": "kubectl version --client"})
            
            if result:
                print("✅ kubectl command executed successfully!")
                print(f"Output: {str(result)[:200]}...")
            else:
                print("❌ No output from kubectl command")
        else:
            print("❌ execute_kubectl tool not found")
            
        # Test kubectl get namespaces command
        await test_kubectl_get_namespaces(mcp_client, tools)
            
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 Testing streamable-http MCP client connection...")
    success = asyncio.run(test_streamable_http_connection())
    
    if success:
        print("\n🎉 All tests passed! Your streamable-http configuration is working correctly.")
    else:
        print("\n💥 Tests failed. Please check your configuration.") 