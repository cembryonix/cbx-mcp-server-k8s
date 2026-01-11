# n8n Integration Example

This example shows how to use the CBX MCP K8s Server with [n8n](https://n8n.io/) workflow automation.

## Architecture

```
┌─────────────┐     ┌─────────────────────┐
│    n8n      │────▶│  CBX MCP K8s Server │
│  (port 5678)│     │     (port 8080)     │
└─────────────┘     └─────────────────────┘
```

## Prerequisites

- Docker and Docker Compose
- Kubernetes config at `~/.kube` (for cluster access)
- (Optional) ArgoCD config at `~/.config/argocd`

## Quick Start

### Option A: Full Docker Stack (Recommended)

Runs both n8n and MCP server in containers.

```bash
cd examples/n8n
docker-compose -f docker-compose-with-mcp.yml up -d
```

You can customize config directories:
```bash
KUBECONFIG_DIR=/path/to/kube ARGOCD_CONFIG_DIR=/path/to/argocd \
  docker-compose -f docker-compose-with-mcp.yml up -d
```

### Option B: MCP Server Running Locally

Runs only n8n in Docker, connects to MCP server running on host.

**1. Start the MCP Server**
```bash
# From the project root
./tests/run-server/from-source/start.sh --host 0.0.0.0 --port 8080
```

**2. Start n8n**
```bash
cd examples/n8n
docker-compose up -d
```

**Note:** After importing, change the workflow's MCP Client endpoint URL to `http://localhost:8080/mcp/`.

### Import Example Workflow

```bash
docker exec -it n8n-n8n-1 n8n import:workflow \
  --input=/home/node/workflows/k8s-agent-example.json
```

### Access n8n

Open http://localhost:5678 in your browser.

### Configure OpenAI Credentials

After importing, set up your OpenAI API key:

1. Open the imported workflow
2. Click on the **OpenAI Chat Model** node
3. Click **Create New Credential**
4. Enter your OpenAI API key
5. Save

### Test the Workflow

1. Open the workflow
2. Click **Chat** in the bottom panel
3. Try: "List all namespaces in the cluster"

## Files

| File | Description |
|------|-------------|
| `docker-compose-with-mcp.yml` | n8n + MCP server (recommended) |
| `docker-compose.yml` | n8n only (requires MCP server running on host) |
| `workflows/` | Example n8n workflow exports |

## Exporting Workflows from n8n

To export a workflow for sharing:

1. Open the workflow in n8n
2. Click the **⋮** menu (top-right)
3. Select **Download**
4. Save the JSON file to `workflows/`

## Troubleshooting

### n8n can't connect to MCP server

1. Ensure the MCP server is running: `curl http://localhost:8080/health`
2. Check MCP server logs: `docker-compose logs mcp-server`
3. Verify network connectivity from n8n container

### Tool calls fail with validation errors

This usually means n8n is sending extra fields. The MCP server middleware should handle this automatically. If issues persist:

1. Enable debug logging: `CBX_MCP_SERVER__LOG_LEVEL=debug`
2. Check for `[Preprocessor]` log messages

### Workflow import fails

Ensure the workflow JSON is valid and was exported from a compatible n8n version (2.3.x).

### Container name differs

If your container is named differently, find it with:
```bash
docker ps --format "table {{.Names}}"
```

---

## Appendix: MCP Proxy for Non-Compliant Servers

n8n sends extra attributes with MCP tool calls (`sessionId`, `toolCallId`, etc.) that are not part of the MCP protocol. The CBX MCP K8s Server handles this with built-in middleware.

However, other MCP servers may fail with validation errors. The `docker-compose-with-proxy.yml` and proxy files (`n8n_mcp_proxy.py`, `Dockerfile.mcp-proxy`) demonstrate how to work around this by stripping these fields before forwarding requests.

These files are provided as a reference for integrating n8n with other MCP servers that lack n8n-compatible middleware.
