#!/usr/bin/env bash

docker run -it \
  --name cbx-mcp-server-k8s \
  -u "$(id -u)":"$(id -g)" \
  -e HOME=/home/appuser \
  -p 8080:8080 \
  -v ~/.kube:/home/appuser/.kube:ro \
  -v ~/.config/argocd:/home/appuser/.config/argocd:ro \
  ghcr.io/cembryonix/cbx-mcp-server-k8s:v0.1.1

#  ghcr.io/cembryonix/cbx-mcp-server-k8s:v0.1.0
# cbx-mcp-server-k8s:develop