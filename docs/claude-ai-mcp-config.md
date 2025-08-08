# Claude.ai configuration: CBX MCP server for K8S




## STDIO transport with Docker
```json
{
  "mcpServers": {
    "kubernetes": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-v",
        "/Users/vkuusk/.kube:/home/appuser/.kube:ro",
        "-e",
        "CBX_CONFIG_NAME=stdio",
        "ghcr.io/cembryonix/cbx-mcp-server-k8s:v0.1.0"
      ]
    }

  }
}
```