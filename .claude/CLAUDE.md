# CBX MCP Server for Kubernetes - Project Context

**Version**: 0.3.1
**Package**: `cbx_mcp_k8s`
**Python**: 3.12+

## Purpose

MCP server providing tools for AI agents to manage Kubernetes and cloud infrastructure. Enables safe execution of CLI tools (kubectl, helm, argocd) with security guardrails.

## Project Structure

```
app/
├── main.py                      # Entry point, CLI args
├── requirements.txt             # Python dependencies
└── cbx_mcp_k8s/
    ├── __init__.py              # Version
    ├── server.py                # FastMCP setup, lifespan, HTTP routes
    ├── config/
    │   ├── models.py            # Pydantic config (K8sMCPServerConfig)
    │   ├── loader.py            # YAML loading, env overrides
    │   └── defaults/            # settings.yaml, security.yaml, tools.yaml
    ├── tools/
    │   ├── base.py              # BaseTool, CliTool classes
    │   └── registry.py          # ToolRegistry, dynamic loading
    ├── executor/
    │   ├── runner.py            # Async subprocess, pipe execution
    │   ├── validator.py         # 3-layer security validation
    │   ├── parser.py            # Command parsing
    │   └── types.py             # Executor type definitions
    ├── session/
    │   ├── base.py              # Session store interface
    │   ├── memory.py            # MemorySessionStore
    │   ├── redis.py             # RedisSessionStore
    │   └── event_store.py       # Event persistence for resumability
    ├── middleware/
    │   └── preprocessor.py      # Filters extra params from non-compliant MCP clients
    ├── resources/               # k8s://cluster/* MCP resources
    ├── prompts/
    │   └── templates.py         # MCP prompt templates
    └── http/
        ├── health.py            # /health, /ready endpoints
        └── metrics.py           # /metrics Prometheus endpoint

examples/n8n/                    # Quick start example (n8n + MCP server)
├── setup.sh                     # One-command setup script
├── docker-compose.yml           # Full stack (n8n + MCP server)
├── docker-compose-local.yml     # n8n only (MCP server on host)
├── workflows/                   # Example n8n workflows
├── images/                      # Screenshots for docs
└── proxy/                       # Reference proxy for non-compliant MCP servers

tests/                           # Integration, functional, standalone tests
pkg/docker/                      # Docker build scripts
```

## Key Components

### Configuration System

```python
# Priority: env vars > user config > defaults
# Env format: CBX_MCP_SERVER__SECTION__KEY (double underscore)

class K8sMCPServerConfig(BaseModel):
    server: ServerSettings      # host, port, transport, log_level
    session: SessionSettings    # persistence, ttl_seconds, redis_url
    command: CommandSettings    # default_timeout, max_output_size
    security: SecuritySettings  # mode, dangerous_commands, safe_patterns
    event_store: EventStoreSettings
```

### Tool System

- **Dynamic loading**: Tools defined in `config/defaults/tools.yaml`
- **CLI tools**: kubectl, helm, argocd - executed via subprocess
- **Auto-prefix**: `get pods` → `kubectl get pods`
- **Discovery**: Validates tool availability at startup

```yaml
# tools.yaml structure
cli_tools:
  kubectl:
    required: true
    check_cmd: "kubectl version --client"
    description: "Kubernetes cluster management"
```

### Security Model (3-Layer)

1. **Prefix blocking**: `dangerous_commands` list (e.g., `kubectl delete`)
2. **Safe patterns**: Exceptions (e.g., `kubectl delete pod` allowed)
3. **Regex rules**: Advanced patterns (block `--all-namespaces` for destructive ops)

```yaml
# security.yaml
security:
  mode: "strict"
  dangerous_commands:
    kubectl: ["kubectl delete", "kubectl drain", ...]
  safe_patterns:
    kubectl: ["kubectl delete pod", ...]
  regex_rules:
    kubectl:
      - pattern: "kubectl\\s+delete.*--all-namespaces"
        action: "block"
```

### Middleware (MCP Protocol Compliance)

`ToolCallPreprocessor` filters extra attributes from non-compliant MCP clients (like n8n) that send fields not in tool schemas (`sessionId`, `toolCallId`, etc.).

```python
# preprocessor.py - whitelist filtering
context.message.arguments = filtered_args  # Only schema-defined params pass through
```

### Session & Event Store

- **Session**: memory (dev) | redis (prod) | sticky (K8s ingress)
- **Event store**: Enables MCP session resumability across pod restarts

## MCP Capabilities

### Tools
| Tool | Function |
|------|----------|
| `k8s_kubectl_execute` | Run kubectl commands |
| `k8s_kubectl_describe` | Get kubectl help |
| `k8s_helm_execute` | Run helm commands |
| `k8s_helm_describe` | Get helm help |
| `k8s_argocd_execute` | Run argocd commands |
| `k8s_argocd_describe` | Get argocd help |
| `k8s_ping` | Health check |

### Resources
- `k8s://cluster/context` - Current kubectl context
- `k8s://cluster/namespaces` - Available namespaces
- `k8s://cluster/info` - Cluster version info

### HTTP Endpoints
- `/health` - Liveness probe
- `/ready` - Readiness probe
- `/metrics` - Prometheus metrics
- `/mcp/` - MCP protocol endpoint

## Running the Server

```bash
# Quick start with n8n (recommended)
cd examples/n8n && ./setup.sh

# From source
./tests/run-server/from-source/start.sh --host 0.0.0.0 --port 8080

# Docker
docker run -p 8080:8080 \
  -v ~/.kube:/home/appuser/.kube:ro \
  ghcr.io/cembryonix/cbx-mcp-server-k8s:0.3.1
```

## Testing

```bash
pytest tests/ -v                              # All tests
pytest tests/integration/test_mcp_protocol.py # Protocol compliance
```

## Common Issues & Fixes

| Issue | Solution |
|-------|----------|
| MCP client validation errors | Middleware filters extra params; check `context.fastmcp_context.fastmcp` path |
| Tool not found | Check `tools.yaml`, verify binary in PATH |
| Security blocks command | Add to `safe_patterns` or adjust `regex_rules` |
| Session not persisting | Check `session.persistence` config, Redis connection |

## Files to Check When Debugging

- `server.py` - Server setup, lifespan, route registration
- `middleware/preprocessor.py` - Filters non-standard params from MCP clients
- `executor/validator.py` - Security validation logic
- `tools/registry.py` - Tool discovery and registration
- `config/defaults/security.yaml` - Security rules

## Version History

- 0.3.1 - n8n example, middleware fixes
- 0.3.0 - FastMCP 2.x rewrite, session management, event store
- 0.2.x - Initial implementation