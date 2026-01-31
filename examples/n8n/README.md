# n8n + CBX MCP Server Example

> **Note:** Uses `docker compose` (modern Docker). For older versions use `docker-compose`.

## Quick Start

```bash
./setup.sh
```

Open http://localhost:5678:
1. [**Set up owner account**](images/n8n-first-config.png) — create your n8n admin account (first time only)
2. **Open the imported workflow** and configure your OpenAI API key in the **OpenAI Chat Model** node

To stop:
```bash
docker compose down
```

## Manual Setup

```bash
docker compose up -d

# Wait for n8n, then import workflow
docker exec n8n-n8n-1 n8n import:workflow \
  --input=/home/node/workflows/k8s-agent-example.json
```

## Custom Config Paths

```bash
KUBECONFIG_DIR=/path/to/kube ARGOCD_CONFIG_DIR=/path/to/argocd ./setup.sh
```

## Alternative: Local MCP Server

```bash
# Terminal 1: Start MCP server
./tests/run-server/from-source/start.sh --host 0.0.0.0 --port 8080

# Terminal 2: Start n8n
docker compose -f docker-compose-local.yml up -d
```

Change workflow endpoint to `http://localhost:8080/mcp/`.

## Files

| File | Description |
|------|-------------|
| `setup.sh` | Quick start script |
| `docker-compose.yml` | Full stack (n8n + MCP server) |
| `docker-compose-local.yml` | n8n only (MCP server on host) |
| `workflows/` | Example workflows |
| `proxy/` | Reference proxy for non-compliant MCP servers |