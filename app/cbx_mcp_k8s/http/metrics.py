"""
Prometheus metrics endpoint.

Provides /metrics endpoint in Prometheus exposition format.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from cbx_mcp_k8s import __version__


@dataclass
class MetricsCollector:
    """
    Simple metrics collector for Prometheus exposition.

    This is a basic implementation. For production, consider using
    prometheus_client library.
    """

    # Counters
    requests_total: int = 0
    tool_calls_total: int = 0
    tool_calls_success: int = 0
    tool_calls_error: int = 0
    tool_calls_blocked: int = 0

    # Gauges
    active_sessions: int = 0

    # Startup time
    start_time: float = field(default_factory=time.time)

    # Per-tool counters
    tool_counts: dict[str, int] = field(default_factory=dict)

    def inc_request(self) -> None:
        """Increment request counter."""
        self.requests_total += 1

    def inc_tool_call(self, tool_name: str, success: bool = True, blocked: bool = False) -> None:
        """Increment tool call counters."""
        self.tool_calls_total += 1

        if blocked:
            self.tool_calls_blocked += 1
        elif success:
            self.tool_calls_success += 1
        else:
            self.tool_calls_error += 1

        # Per-tool counter
        self.tool_counts[tool_name] = self.tool_counts.get(tool_name, 0) + 1

    def format_prometheus(self) -> str:
        """
        Format metrics in Prometheus exposition format.

        Returns:
            Metrics as text in Prometheus format
        """
        uptime = time.time() - self.start_time

        lines = [
            "# HELP cbx_mcp_info Server information",
            "# TYPE cbx_mcp_info gauge",
            f'cbx_mcp_info{{version="{__version__}"}} 1',
            "",
            "# HELP cbx_mcp_uptime_seconds Server uptime in seconds",
            "# TYPE cbx_mcp_uptime_seconds gauge",
            f"cbx_mcp_uptime_seconds {uptime:.2f}",
            "",
            "# HELP cbx_mcp_requests_total Total MCP requests received",
            "# TYPE cbx_mcp_requests_total counter",
            f"cbx_mcp_requests_total {self.requests_total}",
            "",
            "# HELP cbx_mcp_tool_calls_total Total tool calls",
            "# TYPE cbx_mcp_tool_calls_total counter",
            f"cbx_mcp_tool_calls_total {self.tool_calls_total}",
            "",
            "# HELP cbx_mcp_tool_calls_success_total Successful tool calls",
            "# TYPE cbx_mcp_tool_calls_success_total counter",
            f"cbx_mcp_tool_calls_success_total {self.tool_calls_success}",
            "",
            "# HELP cbx_mcp_tool_calls_error_total Failed tool calls",
            "# TYPE cbx_mcp_tool_calls_error_total counter",
            f"cbx_mcp_tool_calls_error_total {self.tool_calls_error}",
            "",
            "# HELP cbx_mcp_tool_calls_blocked_total Blocked tool calls",
            "# TYPE cbx_mcp_tool_calls_blocked_total counter",
            f"cbx_mcp_tool_calls_blocked_total {self.tool_calls_blocked}",
            "",
            "# HELP cbx_mcp_active_sessions Current active sessions",
            "# TYPE cbx_mcp_active_sessions gauge",
            f"cbx_mcp_active_sessions {self.active_sessions}",
        ]

        # Per-tool metrics
        if self.tool_counts:
            lines.extend([
                "",
                "# HELP cbx_mcp_tool_calls_by_name Tool calls by tool name",
                "# TYPE cbx_mcp_tool_calls_by_name counter",
            ])
            for tool_name, count in sorted(self.tool_counts.items()):
                lines.append(f'cbx_mcp_tool_calls_by_name{{tool="{tool_name}"}} {count}')

        return "\n".join(lines) + "\n"


# Global metrics instance (for use without lifespan context)
_global_metrics: Optional[MetricsCollector] = None


def get_global_metrics() -> MetricsCollector:
    """Get or create global metrics collector."""
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = MetricsCollector()
    return _global_metrics


async def metrics_endpoint(request: Request) -> PlainTextResponse:
    """
    Prometheus metrics endpoint.

    Returns:
        Plain text response in Prometheus exposition format
    """
    # Try to get metrics from app state, fall back to global
    metrics = getattr(request.app.state, "metrics", None)
    if metrics is None:
        metrics = get_global_metrics()

    return PlainTextResponse(
        metrics.format_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


def get_metrics_routes(metrics: Optional[MetricsCollector] = None) -> list[Route]:
    """
    Get metrics routes.

    Args:
        metrics: Optional MetricsCollector instance

    Returns:
        List of Starlette Route objects
    """
    return [
        Route("/metrics", metrics_endpoint, methods=["GET"]),
    ]
