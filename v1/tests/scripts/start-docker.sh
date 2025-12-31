#!/usr/bin/env bash

docker run -it \
  --name cbx-mcp-server-k8s \
  --rm \
  -e HOME=/home/appuser \
  -e CBX_MCP_SERVER_TRANSPORT_TYPE=http \
  -p 8080:8080 \
  -v ~/.kube:/home/appuser/.kube:ro \
  -v ~/.config/argocd:/home/appuser/.config/argocd:ro \
  cbx-mcp-server-k8s:develop

#  ghcr.io/cembryonix/cbx-mcp-server-k8s:v0.1.0
# cbx-mcp-server-k8s:develop

#   -u "$(id -u)":"$(id -g)" \