# Docker HTTP Quickstart

Run the CBX MCP Server for Kubernetes in a Docker container with HTTP transport.

## Prerequisites

- Docker installed
- Kubernetes config at `~/.kube/` (for kubectl access)
- ArgoCD config at `~/.config/argocd/` (optional, for argocd access)

## Start the Server

```bash
./start-docker.sh
```

This will:
- Pull the image from GitHub Container Registry (`ghcr.io/cembryonix/cbx-mcp-server-k8s`)
- Start the container with HTTP transport on port 8080
- Mount your `~/.kube` and `~/.config/argocd` directories (read-only)

**Server endpoint:** `http://127.0.0.1:8080/mcp`

## Test the Server

### Quick Test with curl

```bash
# Test MCP initialization
curl -X POST http://127.0.0.1:8080/mcp \
  -H "Content-Type: application/json" \
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

### Run Validation Tests

From the repository root (with venv activated):

```bash
# Basic validation
python tests/validation/validation-mcp-client.py live \
  --transport http \
  --server-url http://127.0.0.1:8080/mcp

# With verbose output
python tests/validation/validation-mcp-client.py live \
  --transport http \
  --server-url http://127.0.0.1:8080/mcp \
  --verbose
```

### Run Capability Audit

```bash
python tests/scripts/capability_audit.py \
  --server-url http://127.0.0.1:8080/mcp \
  --transport streamable_http
```

## Stop the Server

Press `Ctrl+C` in the terminal where the container is running, or:

```bash
docker stop cbx-mcp-server-k8s
```

## Configuration

The container uses HTTP transport by default. Environment variables can override settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `CBX_MCP_SERVER_TRANSPORT_TYPE` | `http` | Transport type |
| `CBX_MCP_SERVER_PORT` | `8080` | Server port |
| `CBX_MCP_SERVER_LOG_LEVEL` | `INFO` | Log level |
| `CBX_MCP_SECURITY_SECURITY_MODE` | `strict` | Security mode (`strict` or `permissive`) |

Example with custom settings:

```bash
docker run -it --rm \
  --name cbx-mcp-server-k8s \
  -e CBX_MCP_SERVER_LOG_LEVEL=DEBUG \
  -p 8080:8080 \
  -v ~/.kube:/home/appuser/.kube:ro \
  ghcr.io/cembryonix/cbx-mcp-server-k8s:v0.2.0
```