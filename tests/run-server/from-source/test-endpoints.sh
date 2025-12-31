#!/bin/bash
#
# Quick test of server endpoints
# Run this while the server is running to verify it's working
#

HOST="${1:-127.0.0.1}"
PORT="${2:-8765}"
BASE_URL="http://$HOST:$PORT"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "Testing server at $BASE_URL"
echo "================================"
echo ""

# Health check
echo "1. Health Check (/health)"
HEALTH=$(curl -s "$BASE_URL/health")
if echo "$HEALTH" | grep -q '"status":"healthy"'; then
    echo -e "   ${GREEN}PASS${NC}: $HEALTH"
else
    echo -e "   ${RED}FAIL${NC}: $HEALTH"
fi
echo ""

# Ready check
echo "2. Ready Check (/ready)"
READY=$(curl -s "$BASE_URL/ready")
if echo "$READY" | grep -q '"status":"ready"'; then
    echo -e "   ${GREEN}PASS${NC}: $READY"
else
    echo -e "   ${RED}FAIL${NC}: $READY"
fi
echo ""

# Metrics
echo "3. Metrics (/metrics)"
METRICS=$(curl -s "$BASE_URL/metrics" | head -5)
if echo "$METRICS" | grep -q 'cbx_mcp'; then
    echo -e "   ${GREEN}PASS${NC}: Prometheus metrics available"
    echo "$METRICS" | sed 's/^/   /'
else
    echo -e "   ${RED}FAIL${NC}: No metrics"
fi
echo ""

# MCP Initialize
echo "4. MCP Initialize (/mcp)"
MCP_INIT=$(curl -s -X POST "$BASE_URL/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"}
        }
    }')
if echo "$MCP_INIT" | grep -q '"result"'; then
    echo -e "   ${GREEN}PASS${NC}: MCP initialized"
    echo "$MCP_INIT" | head -c 200
    echo "..."
else
    echo -e "   ${RED}FAIL${NC}: $MCP_INIT"
fi
echo ""
echo ""
echo "================================"
echo "Done!"
