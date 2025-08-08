#!/usr/bin/env bash

version="v0.1.0"

docker run -d \
  --name cbx-mcp-server-k8s \
  --restart unless-stopped \
  -p 8080:8080 \
  -v ~/.kube:/home/appuser/.kube:ro \
  ghcr.io/vkuusk/cbx-mcp-server-k8s:${version}

  # cbx-mcp-server-k8s:develop