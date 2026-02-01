# Server Configuration

This document describes all configuration options for the CBX MCP K8s Server when running the prebuilt Docker image.

## Configuration Methods

Configuration is applied in the following priority (highest to lowest):

1. **Environment variables** — Override any setting
2. **Mounted config files** — YAML files in config directory
3. **Built-in defaults** — Packaged in the Docker image

### Environment Variables

Use the format `CBX_MCP_<SECTION>__<KEY>=value` (double underscore separates nested keys).

```bash
docker run \
  -e CBX_MCP_SERVER__PORT=9000 \
  -e CBX_MCP_SERVER__LOG_LEVEL=debug \
  -e CBX_MCP_SESSION__PERSISTENCE=redis \
  -e CBX_MCP_SESSION__REDIS_URL=redis://redis:6379/0 \
  ghcr.io/cembryonix/cbx-mcp-server-k8s:0.3.1
```

### Config Files

Mount a directory containing `config.yaml` and/or `security.yaml`:

```bash
docker run \
  -v /path/to/my-configs:/home/appuser/app_configs \
  ghcr.io/cembryonix/cbx-mcp-server-k8s:0.3.1
```

Or specify a custom config directory:

```bash
docker run \
  -e CBX_MCP_CONFIG_DIR=/custom/path \
  -v /path/to/my-configs:/custom/path \
  ghcr.io/cembryonix/cbx-mcp-server-k8s:0.3.1
```

---

## Configuration Reference

### Server Settings

Controls how the MCP server listens for connections.

| Variable | Config Key | Default | Description |
|----------|------------|---------|-------------|
| `CBX_MCP_SERVER__HOST` | `server.host` | `0.0.0.0` | Host to bind to |
| `CBX_MCP_SERVER__PORT` | `server.port` | `8080` | Port to listen on (1-65535) |
| `CBX_MCP_SERVER__TRANSPORT` | `server.transport` | `streamable-http` | Transport protocol: `streamable-http` or `stdio` |
| `CBX_MCP_SERVER__LOG_LEVEL` | `server.log_level` | `info` | Log level: `debug`, `info`, `warning`, `error` |

**Example config.yaml:**
```yaml
server:
  host: "0.0.0.0"
  port: 8080
  transport: "streamable-http"
  log_level: "info"
```

---

### Session Settings

Controls MCP session storage. Sessions store application state for connected clients.

| Variable | Config Key | Default | Description |
|----------|------------|---------|-------------|
| `CBX_MCP_SESSION__PERSISTENCE` | `session.persistence` | `memory` | Storage backend: `memory`, `redis`, `sticky` |
| `CBX_MCP_SESSION__TTL_SECONDS` | `session.ttl_seconds` | `3600` | Session timeout (minimum 60) |
| `CBX_MCP_SESSION__REDIS_URL` | `session.redis_url` | — | Redis URL (required if persistence=redis) |

**Persistence options:**
- `memory` — In-memory storage, single pod only (default)
- `redis` — Redis-backed, supports multiple pods
- `sticky` — Relies on Kubernetes ingress sticky sessions

**Example config.yaml:**
```yaml
session:
  persistence: "redis"
  ttl_seconds: 3600
  redis_url: "redis://redis:6379/0"
```

---

### Event Store Settings

Controls MCP protocol resumability. Enables clients to reconnect after disconnection and replay missed events.

| Variable | Config Key | Default | Description |
|----------|------------|---------|-------------|
| `CBX_MCP_EVENT_STORE__PERSISTENCE` | `event_store.persistence` | `none` | Backend: `none`, `memory`, `redis` |
| `CBX_MCP_EVENT_STORE__REDIS_URL` | `event_store.redis_url` | — | Redis URL (required if persistence=redis) |
| `CBX_MCP_EVENT_STORE__MAX_EVENTS` | `event_store.max_events` | `1000` | Max events per session (10-10000) |
| `CBX_MCP_EVENT_STORE__TTL_SECONDS` | `event_store.ttl_seconds` | `3600` | Event TTL (minimum 60) |

**Persistence options:**
- `none` — Disabled, no resumability (default)
- `memory` — In-memory, single pod only
- `redis` — Redis Streams, supports multiple pods (recommended for production)

**Example config.yaml:**
```yaml
event_store:
  persistence: "redis"
  redis_url: "redis://redis:6379/1"
  max_events: 1000
  ttl_seconds: 3600
```

---

### Command Settings

Controls CLI command execution limits.

| Variable | Config Key | Default | Description |
|----------|------------|---------|-------------|
| `CBX_MCP_COMMAND__DEFAULT_TIMEOUT` | `command.default_timeout` | `60` | Command timeout in seconds (1-600) |
| `CBX_MCP_COMMAND__MAX_OUTPUT_SIZE` | `command.max_output_size` | `100000` | Max output bytes before truncation |

**Example config.yaml:**
```yaml
command:
  default_timeout: 120
  max_output_size: 200000
```

---

### Security Settings

Controls command validation and security guardrails.

| Variable | Config Key | Default | Description |
|----------|------------|---------|-------------|
| `CBX_MCP_SECURITY__MODE` | `security.mode` | `strict` | Validation mode: `strict` or `permissive` |

**Security mode:**
- `strict` — Validates all commands against security rules (default)
- `permissive` — Disables all validation (use with caution)

Security rules (`dangerous_commands`, `safe_patterns`, `regex_rules`, `allowed_unix_commands`) must be configured via `security.yaml` file — they cannot be set via environment variables due to their complexity.

**Example security.yaml:**
```yaml
security:
  mode: "strict"

  # Commands blocked by default
  dangerous_commands:
    kubectl:
      - "kubectl delete"
      - "kubectl drain"

  # Exceptions to dangerous commands
  safe_patterns:
    kubectl:
      - "kubectl delete pod"
      - "kubectl delete deployment"

  # Regex-based rules
  regex_rules:
    kubectl:
      - pattern: "kubectl\\s+delete\\s+.*--all-namespaces"
        action: "block"
        message: "Deleting across all namespaces is restricted"

  # Unix commands allowed in pipes
  allowed_unix_commands:
    - "grep"
    - "jq"
    - "head"
    - "tail"
```

---

## Common Deployment Examples

### Single Pod (Development)

```bash
docker run -p 8080:8080 \
  -v ~/.kube:/home/appuser/.kube:ro \
  ghcr.io/cembryonix/cbx-mcp-server-k8s:0.3.1
```

### Multi-Pod with Redis (Production)

```bash
docker run -p 8080:8080 \
  -v ~/.kube:/home/appuser/.kube:ro \
  -e CBX_MCP_SESSION__PERSISTENCE=redis \
  -e CBX_MCP_SESSION__REDIS_URL=redis://redis:6379/0 \
  -e CBX_MCP_EVENT_STORE__PERSISTENCE=redis \
  -e CBX_MCP_EVENT_STORE__REDIS_URL=redis://redis:6379/1 \
  ghcr.io/cembryonix/cbx-mcp-server-k8s:0.3.1
```

### Custom Security Rules

```bash
docker run -p 8080:8080 \
  -v ~/.kube:/home/appuser/.kube:ro \
  -v /path/to/my-security.yaml:/home/appuser/app_configs/security.yaml:ro \
  ghcr.io/cembryonix/cbx-mcp-server-k8s:0.3.1
```

### Debug Mode

```bash
docker run -p 8080:8080 \
  -v ~/.kube:/home/appuser/.kube:ro \
  -e CBX_MCP_SERVER__LOG_LEVEL=debug \
  ghcr.io/cembryonix/cbx-mcp-server-k8s:0.3.1
```

---

## CLI Tool Configuration

CLI tools (kubectl, helm, argocd) run in subprocesses that **inherit the server's environment as-is**. The MCP server does not modify or intercept environment variables — standard tool configuration applies.

| Variable | Used By | Default |
|----------|---------|---------|
| `KUBECONFIG` | kubectl, helm | `~/.kube/config` |
| `ARGOCD_SERVER` | argocd | — |
| `ARGOCD_AUTH_TOKEN` | argocd | — |

---

## Volume Mounts

The Docker image expects these volume mounts for credentials:

| Path | Purpose |
|------|---------|
| `/home/appuser/.kube` | Kubernetes config (kubeconfig) |
| `/home/appuser/.config/argocd` | ArgoCD config (optional) |
| `/home/appuser/.aws` | AWS credentials (optional) |
| `/home/appuser/app_configs` | Server configuration files |