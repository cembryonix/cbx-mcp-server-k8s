"""
HTTP endpoints for health checks and metrics.

Provides:
- /health: Kubernetes liveness probe
- /ready: Kubernetes readiness probe
- /metrics: Prometheus-format metrics
"""

from cbx_mcp_k8s.http.health import get_health_routes, health_check, ready_check
from cbx_mcp_k8s.http.metrics import (
    get_metrics_routes,
    metrics_endpoint,
    MetricsCollector,
    get_global_metrics,
)

__all__ = [
    "get_health_routes",
    "health_check",
    "ready_check",
    "get_metrics_routes",
    "metrics_endpoint",
    "MetricsCollector",
    "get_global_metrics",
]
