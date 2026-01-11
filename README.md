# CBX MCP Server for Kubernetes ![version](https://img.shields.io/badge/version-0.3.1-blue)

An MCP server providing tools for AI agents to manage Kubernetes and cloud infrastructure.

Part of the [Cembryonix Project](https://github.com/cembryonix) collection.

## Overview

This server enables AI agents to interact with Kubernetes clusters and related cloud services. While the current release focuses on Kubernetes and ArgoCD, cloud-specific tools (AWS EKS, GCP GKE, Azure AKS) are coming soon.

## Quick Start

Run the full example with n8n agent using Docker:

```bash
cd examples/n8n
docker-compose -f docker-compose-with-mcp.yml up -d
```

See [examples/n8n/README.md](examples/n8n/README.md) for setup details.

## Key Features

- **Dynamic Tool Loading** — Tools are loaded from configuration, making the server easily expandable and tunable. Not limited to Kubernetes; can be configured for any CLI.

- **Security Guardrails** — Configure which command options should be blocked to prevent dangerous operations (e.g., `--force`, `--all-namespaces` for destructive commands).

- **Pipeline Execution** — Built-in support for executing multi-step command pipelines.

- **n8n Compatible** — Middleware handles n8n-specific attributes that other MCP servers may reject.

## Available Tools

| Tool | Description |
|------|-------------|
| `kubectl` | Kubernetes cluster management |
| `helm` | Helm chart operations |
| `argocd` | ArgoCD GitOps operations |
| *Cloud tools* | Coming soon (EKS, GKE, AKS) |

## Installation

```bash
# From Docker image
docker pull ghcr.io/cembryonix/cbx-mcp-server-k8s:0.3.1

# From source
git clone https://github.com/cembryonix/cbx-mcp-server-k8s.git
cd cbx-mcp-server-k8s
pip install -e .
```

## Configuration

The server uses YAML configuration files in `app/cbx_mcp_k8s/config/defaults/`:
- `tools.yaml` — Define available CLI tools
- `security.yaml` — Security rules and guardrails
- `settings.yaml` — Server settings

Environment variables override config using Pydantic's nested model convention:
`CBX_MCP_SERVER__SECTION__KEY=value` (double underscores separate nested keys)

## License

Apache 2.0