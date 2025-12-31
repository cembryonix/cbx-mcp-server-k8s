"""
Health check endpoint for Kubernetes probes.

Provides /health endpoint for liveness and readiness probes.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from cbx_mcp_k8s import __version__


async def health_check(request: Request) -> JSONResponse:
    """
    Kubernetes liveness/readiness probe endpoint.

    Returns:
        JSON response with health status
    """
    return JSONResponse(
        {
            "status": "healthy",
            "version": __version__,
            "service": "cbx_mcp_k8s",
        }
    )


async def ready_check(request: Request) -> JSONResponse:
    """
    Readiness probe endpoint.

    Can be extended to check dependencies (Redis, etc.)

    Returns:
        JSON response with readiness status
    """
    # TODO: Add dependency checks when session stores are implemented
    checks = {
        "server": True,
        # "redis": check_redis_connection(),
        # "kubectl": check_kubectl_available(),
    }

    all_ready = all(checks.values())

    return JSONResponse(
        {
            "status": "ready" if all_ready else "not_ready",
            "checks": checks,
        },
        status_code=200 if all_ready else 503,
    )


def get_health_routes() -> list[Route]:
    """
    Get health check routes.

    Returns:
        List of Starlette Route objects
    """
    return [
        Route("/health", health_check, methods=["GET"]),
        Route("/ready", ready_check, methods=["GET"]),
    ]
