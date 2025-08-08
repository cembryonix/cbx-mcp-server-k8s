#!/usr/bin/env bash

version="v0.1.1"

docker run -d \
  --name cbx-mcp-server-k8s \
  --restart unless-stopped \
  -u "$(id -u)":"$(id -g)" \
  -e HOME=/home/appuser \
  -p 8080:8080 \
  -v ~/.kube:/home/appuser/.kube:ro \
  -v ~/.config/argocd:/home/appuser/.config/argocd:ro \
  ghcr.io/vkuusk/cbx-mcp-server-k8s:${version}
