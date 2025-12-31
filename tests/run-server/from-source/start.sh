#!/bin/bash
#
# Start MCP K8s Server from source code
#
# Prerequisites:
#   - Python venv activated
#   - kubectl, helm installed (required)
#   - argocd installed (optional)
#
# Usage:
#   ./start.sh                # Start with HTTP transport (default)
#   ./start.sh -t http        # Explicit HTTP transport
#   ./start.sh -t stdio       # Use stdio transport
#   ./start.sh --skip-validation  # Skip tool validation
#
# HTTP server endpoints:
#   http://127.0.0.1:8765/mcp     (MCP endpoint)
#   http://127.0.0.1:8765/health  (Health check)
#   http://127.0.0.1:8765/ready   (Readiness check)
#   http://127.0.0.1:8765/metrics (Prometheus metrics)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/../../../app"
CONFIG_DIR="$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
TRANSPORT="streamable-http"
SKIP_VALIDATION=""
EXTRA_ARGS=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--transport)
            case $2 in
                stdio)
                    TRANSPORT="stdio"
                    ;;
                http|streamable-http)
                    TRANSPORT="streamable-http"
                    ;;
                *)
                    echo -e "${RED}ERROR: Invalid transport '$2'. Use 'stdio' or 'http'${NC}"
                    exit 1
                    ;;
            esac
            shift 2
            ;;
        --skip-validation)
            SKIP_VALIDATION="--skip-tool-validation"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -t, --transport TYPE   Transport mode: stdio or http (default: http)"
            echo "  --skip-validation      Skip tool availability validation"
            echo "  -h, --help             Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                     # Start HTTP server on port 8765"
            echo "  $0 -t stdio            # Start in stdio mode for MCP clients"
            echo "  $0 --skip-validation   # Start without checking kubectl/helm"
            exit 0
            ;;
        *)
            EXTRA_ARGS="$EXTRA_ARGS $1"
            shift
            ;;
    esac
done

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}CBX MCP K8s Server - Manual Test Runner${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if venv is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}Warning: No virtual environment detected${NC}"
    echo "Consider activating venv first:"
    echo "  source /path/to/venv/bin/activate"
    echo ""
fi

# Check required tools (skip if validation is disabled)
if [ -z "$SKIP_VALIDATION" ]; then
    echo "Checking required tools..."
    if ! command -v kubectl &> /dev/null; then
        echo -e "${RED}ERROR: kubectl not found${NC}"
        echo "Use --skip-validation to start without kubectl"
        exit 1
    fi
    echo -e "  kubectl: ${GREEN}OK${NC}"

    if ! command -v helm &> /dev/null; then
        echo -e "${RED}ERROR: helm not found${NC}"
        echo "Use --skip-validation to start without helm"
        exit 1
    fi
    echo -e "  helm: ${GREEN}OK${NC}"

    if command -v argocd &> /dev/null; then
        echo -e "  argocd: ${GREEN}OK${NC} (optional)"
    else
        echo -e "  argocd: ${YELLOW}not found${NC} (optional, skipping)"
    fi
    echo ""
else
    echo -e "${YELLOW}Skipping tool validation${NC}"
    echo ""
fi

echo "Starting server..."
echo "  Transport: $TRANSPORT"
echo "  Config:    $CONFIG_DIR/config.yaml"
echo "  App:       $APP_DIR/main.py"

if [ "$TRANSPORT" = "streamable-http" ]; then
    echo ""
    echo "Server will be available at:"
    echo "  http://127.0.0.1:8765/mcp     (MCP endpoint)"
    echo "  http://127.0.0.1:8765/health  (Health check)"
fi

echo ""

# Run the server
cd "$APP_DIR"
exec python main.py \
    --config-dir "$CONFIG_DIR" \
    --transport "$TRANSPORT" \
    $SKIP_VALIDATION \
    $EXTRA_ARGS
