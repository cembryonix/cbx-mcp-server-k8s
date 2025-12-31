# CBX MCP K8s Server - Docker Build
ARG PYTHON_VERSION=3.12-slim

FROM python:${PYTHON_VERSION}
ARG TARGETPLATFORM
ARG TARGETARCH

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    tar \
    gzip \
    && rm -rf /var/lib/apt/lists/*

# Create directories for binaries
RUN mkdir -p /opt/bin

# Install kubectl
ARG KUBECTL_VERSION=v1.33.0
RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/arm64/kubectl"; \
    else \
        curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"; \
    fi \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/

# Install Helm
ARG HELM_VERSION=v3.17.3
RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        curl -LO "https://get.helm.sh/helm-${HELM_VERSION}-linux-arm64.tar.gz" && \
        tar -zxvf helm-${HELM_VERSION}-linux-arm64.tar.gz && \
        mv linux-arm64/helm /usr/local/bin/helm && \
        rm -rf linux-arm64 helm-${HELM_VERSION}-linux-arm64.tar.gz; \
    else \
        curl -LO "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" && \
        tar -zxvf helm-${HELM_VERSION}-linux-amd64.tar.gz && \
        mv linux-amd64/helm /usr/local/bin/helm && \
        rm -rf linux-amd64 helm-${HELM_VERSION}-linux-amd64.tar.gz; \
    fi && chmod +x /usr/local/bin/helm

# Install ArgoCD CLI
ARG ARGOCD_VERSION=v2.14.11
RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/download/${ARGOCD_VERSION}/argocd-linux-arm64; \
    else \
        curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/download/${ARGOCD_VERSION}/argocd-linux-amd64; \
    fi \
    && chmod +x argocd \
    && mv argocd /usr/local/bin/

# Install runtime dependencies and utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    less \
    jq \
    gnupg \
    tar \
    gzip \
    zip \
    vim \
    net-tools \
    dnsutils \
    openssh-client \
    grep \
    sed \
    gawk \
    findutils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install yq
ARG YQ_VERSION=v4.44.1
RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        curl -sSL -o /usr/local/bin/yq https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_linux_arm64; \
    else \
        curl -sSL -o /usr/local/bin/yq https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_linux_amd64; \
    fi \
    && chmod +x /usr/local/bin/yq

# Set up user and directories
RUN groupadd -g 10001 appgroup \
    && useradd -m -s /bin/bash -u 10001 -g appgroup appuser \
    && mkdir -p /home/appuser/.kube \
    && mkdir -p /home/appuser/.aws \
    && mkdir -p /home/appuser/.config/gcloud \
    && mkdir -p /home/appuser/.azure \
    && mkdir -p /home/appuser/.oci \
    && mkdir -p /home/appuser/app_configs \
    && mkdir -p /app/logs \
    && chown -R appuser:appgroup /home/appuser \
    && chown -R appuser:appgroup /app \
    && chmod 700 /home/appuser/.kube \
    && chmod 700 /home/appuser/.aws \
    && chmod 700 /home/appuser/.config/gcloud \
    && chmod 700 /home/appuser/.azure \
    && chmod 700 /home/appuser/.oci \
    && chmod 750 /app/logs

WORKDIR /app

# Copy and install Python dependencies first (for caching)
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt \
    && find /usr/local/lib/python3.12/site-packages -name "*.pyc" -delete \
    && find /usr/local/lib/python3.12/site-packages -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Copy application code
COPY README.md LICENSE NOTICE ./
COPY app/main.py ./
COPY app/cbx_mcp_k8s/ ./cbx_mcp_k8s/
COPY pkg/docker/entrypoint.sh ./
COPY pkg/docker/server_configs/default_config.yaml /home/appuser/app_configs/settings.yaml

# Fix ownership and permissions
RUN chmod +x /app/entrypoint.sh \
    && chown -R appuser:appgroup /app \
    && chown -R appuser:appgroup /home/appuser/app_configs

# Switch to application user
USER appuser

# Environment variables
ENV HOME="/home/appuser" \
    PATH="/usr/local/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONOPTIMIZE=1

# Labels
LABEL org.opencontainers.image.title="CBX MCP Server for K8S" \
      org.opencontainers.image.description="CBX MCP server - proxy for CLIs to manage Kubernetes" \
      org.opencontainers.image.source="https://github.com/cembryonix/cbx-mcp-server-kubernetes" \
      org.opencontainers.image.version="0.3.0"

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
