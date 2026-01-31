#!/bin/bash
# Setup script for n8n + CBX MCP Server example
# Usage: ./setup.sh

set -e

echo "Starting n8n + MCP server..."
docker compose up -d

echo "Waiting for n8n to be ready..."
until docker exec n8n-n8n-1 wget -q --spider http://localhost:5678/healthz 2>/dev/null; do
  sleep 2
  echo "  waiting..."
done

echo "Importing example workflow..."
docker exec n8n-n8n-1 n8n import:workflow --input=/home/node/workflows/k8s-agent-example.json

echo ""
echo "Setup complete!"
echo "  Open: http://localhost:5678"
echo "  Configure your OpenAI API key in the workflow's OpenAI Chat Model node"