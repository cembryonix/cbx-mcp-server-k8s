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

## STDIO transport from local code
```json
{
    "mcpServers": {
      "kubernetes": {
        "command": "<PATH_TO_CODE_DIR>/cbx-mcp-server-k8s/venv/bin/python",
        "args": [
          "<PATH_TO_CODE_DIR>/cbx-mcp-server-k8s/app/main.py",
          "--config-dir",
          "<PATH_TO_CODE_DIR>/cbx-mcp-server-k8s/tests/server-configs/stdio"
        ]
      }
    },
    "preferences": {
      "quickEntryShortcut": "off",
      "menuBarEnabled": false
    }
  }

```