#!/usr/bin/env bash

docker run -d \
  --name cbx-mcp-server-k8s \
  --restart unless-stopped \
  -p 8080:8080 \
  -v ~/.kube:/home/appuser/.kube:ro \
  ghcr.io/cembryonix/cbx-mcp-server-k8s:v0.1.0
# cbx-mcp-server-k8s:develop