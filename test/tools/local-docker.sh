#!/usr/bin/env bash

# Test if your container responds to MCP initialization
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0.0"}}}' | docker run -i --rm -v /Users/vkuusk/.kube:/home/appuser/.kube:ro cbx-mcp-server-k8s:develop