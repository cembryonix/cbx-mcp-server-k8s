#!/bin/bash
set -e

# CBX MCP K8s Server Entrypoint
# Supports both HTTP (default) and stdio transport modes

TRANSPORT="${CBX_MCP_TRANSPORT:-streamable-http}"
HOST="${CBX_MCP_HOST:-0.0.0.0}"
PORT="${CBX_MCP_PORT:-8080}"
CONFIG_DIR="${CBX_MCP_CONFIG_DIR:-/home/appuser/app_configs}"

echo "Starting CBX MCP K8s Server..."
echo "  Transport: ${TRANSPORT}"
echo "  Config dir: ${CONFIG_DIR}"

if [ "${TRANSPORT}" = "stdio" ]; then
    exec python3 /app/main.py \
        --transport stdio \
        --config-dir "${CONFIG_DIR}"
else
    echo "  Host: ${HOST}"
    echo "  Port: ${PORT}"
    exec python3 /app/main.py \
        --transport streamable-http \
        --host "${HOST}" \
        --port "${PORT}" \
        --config-dir "${CONFIG_DIR}"
fi
