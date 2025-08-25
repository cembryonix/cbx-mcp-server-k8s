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
        "<YOUR_USER_HOME>/.kube:/home/appuser/.kube:ro",
        "-v",
        "<YOUR_USER_HOME>/.config/argocd:/home/appuser/.config/argocd:ro",
        "-e",
        "CBX_MCP_SERVER_TRANSPORT_TYPE=stdio",
        "cbx-mcp-server-k8s:develop"
      ]
    }

  }
}
```