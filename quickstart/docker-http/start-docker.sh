#!/usr/bin/env bash

gh_owner="cembryonix"
version="v0.2.0"

docker run -it --rm \
  --name cbx-mcp-server-k8s \
  -e HOME=/home/appuser \
  -e CBX_MCP_SERVER_TRANSPORT_TYPE=http \
  -p 8080:8080 \
  -v ~/.kube:/home/appuser/.kube:ro \
  -v ~/.config/argocd:/home/appuser/.config/argocd:ro \
  ghcr.io/${gh_owner}/cbx-mcp-server-k8s:${version}
