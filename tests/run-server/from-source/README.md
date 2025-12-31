# Manual Server Testing

Scripts for running the MCP K8s server from source code for manual testing.

## Prerequisites

1. Python virtual environment activated
2. Required CLI tools installed:
   - `kubectl` (required)
   - `helm` (required)
   - `argocd` (optional)

## Quick Start

```bash
# From this directory
./start.sh

# Or from project root
./tests/run-server/from-source/start.sh
```

## Server Endpoints

Once running, the server is available at:

| Endpoint | Description |
|----------|-------------|
| `http://127.0.0.1:8765/mcp` | MCP JSON-RPC endpoint |
| `http://127.0.0.1:8765/health` | Kubernetes liveness probe |
| `http://127.0.0.1:8765/ready` | Kubernetes readiness probe |
| `http://127.0.0.1:8765/metrics` | Prometheus metrics |

## Testing Endpoints

```bash
# Health check
curl http://127.0.0.1:8765/health

# Readiness (shows registered tools)
curl http://127.0.0.1:8765/ready

# Metrics
curl http://127.0.0.1:8765/metrics

# MCP Initialize
curl -X POST http://127.0.0.1:8765/mcp \
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
  }'
```

## Configuration

Edit `config.yaml` to customize:
- Server host/port
- Command timeouts
- Security mode (strict/permissive)

## CLI Options

```bash
# Override port
./start.sh --port 9000

# Override host
./start.sh --host 0.0.0.0

# Use stdio transport (for local MCP clients)
./start.sh --transport stdio
```
