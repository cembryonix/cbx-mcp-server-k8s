#!/usr/bin/env bash

# Quick test: verify docker container responds to MCP initialization via stdio
# Usage: ./test-docker-stdio.sh [image_name]

IMAGE="${1:-cbx-mcp-server-k8s:develop}"

echo "Testing MCP initialization with image: $IMAGE"
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0.0"}}}' | \
  docker run -i --rm \
    -v "${HOME}/.kube:/home/appuser/.kube:ro" \
    "$IMAGE"