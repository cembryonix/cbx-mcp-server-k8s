# CBX MCP Server for Kubernetes ![version](https://img.shields.io/badge/version-0.3.1-blue)

An MCP server providing tools for AI agents to manage Kubernetes and cloud infrastructure.

Part of the [Cembryonix Project](https://github.com/cembryonix) collection.

## Quick Start

```bash
cd examples/n8n
./setup.sh
```

Open http://localhost:5678:
1. **Set up owner account** — create your n8n admin account (first time only)
2. **Open the imported workflow** and configure your OpenAI API key

To stop: `docker compose down`

See [examples/n8n/README.md](examples/n8n/README.md) for more options.

## Features

- **Dynamic Tool Loading** — Tools loaded from config, easily expandable
- **Security Guardrails** — Block dangerous command patterns
- **Pipeline Execution** — Multi-step command pipelines
- **n8n Compatible** — Middleware handles n8n-specific attributes

## Available Tools

| Tool | Description |
|------|-------------|
| `kubectl` | Kubernetes cluster management |
| `helm` | Helm chart operations |
| `argocd` | ArgoCD GitOps operations |

## Configuration

**Environment variables** (recommended for Docker):
```
CBX_MCP_SERVER__PORT=9000
CBX_MCP_SESSION__PERSISTENCE=redis
CBX_MCP_SESSION__REDIS_URL=redis://localhost:6379
```

**Config files** (mount to `/home/appuser/app_configs`):
- `config.yaml` — Server settings
- `security.yaml` — Security rules

Priority: env vars > mounted config > built-in defaults

See [docs/server-configuration.md](docs/server-configuration.md) for full reference.

## License

Apache 2.0