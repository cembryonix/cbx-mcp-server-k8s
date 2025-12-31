"""
FastMCP Server Setup.

This module creates and configures the MCP server instance.
"""

import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from cbx_mcp_k8s import __version__
from cbx_mcp_k8s.config import K8sMCPServerConfig
from cbx_mcp_k8s.http.metrics import MetricsCollector
from cbx_mcp_k8s.session import create_event_store, create_session_store


@dataclass
class ExecutorConfig:
    """Configuration passed to tools for command execution."""

    default_timeout: int
    max_output_size: int
    security_config: dict[str, Any] | None


@dataclass
class ServerBundle:
    """Bundle containing server and related components."""

    server: FastMCP
    event_store: Any  # RedisEventStore | InMemoryEventStore | None


async def create_server_async(
    config: K8sMCPServerConfig,
    tools_config_path: Path | None = None,
    skip_tool_validation: bool = False,
) -> ServerBundle:
    """
    Create and configure the MCP server (async version).

    This async version allows tool discovery before server creation.

    Args:
        config: Server configuration
        tools_config_path: Optional path to tools.yaml config
        skip_tool_validation: Skip tool availability validation (for testing)

    Returns:
        ServerBundle containing FastMCP instance and event store

    Raises:
        RuntimeError: If required tools are not available
    """
    from cbx_mcp_k8s.tools import ToolRegistry

    # Create metrics collector for tracking
    metrics = MetricsCollector()

    # Create executor config for tools
    executor_config = ExecutorConfig(
        default_timeout=config.command.default_timeout,
        max_output_size=config.command.max_output_size,
        security_config=config.security.model_dump() if config.security else None,
    )

    # Create tool registry and discover tools BEFORE server creation
    tool_registry = ToolRegistry(executor_config)
    tool_registry.load_config(tools_config_path)

    # Track registered tools for readiness check
    registered_tools: list[str] = []

    # Discover and validate tools now (before server creation)
    if not skip_tool_validation:
        print("Discovering available tools...", file=sys.stderr)
        result = await tool_registry.discover_and_validate(
            skip_connectivity_test=False
        )

        if not result.success:
            print("ERROR: Required tools not available!", file=sys.stderr)
            print(result.summary(), file=sys.stderr)
            raise RuntimeError(
                f"Required tools not available: {result.failed_required}"
            )

        print(result.summary(), file=sys.stderr)
        registered_tools = result.registered_tools

    # Create event store for MCP protocol resumability (pod restart resilience)
    event_store = create_event_store(
        persistence=config.event_store.persistence.value,
        redis_url=config.event_store.redis_url,
        max_events=config.event_store.max_events,
        ttl_seconds=config.event_store.ttl_seconds,
    )

    if event_store:
        print(
            f"Event store created (persistence={config.event_store.persistence.value})",
            file=sys.stderr,
        )

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
        """
        Server lifespan manager.

        Initializes resources at startup and cleans up at shutdown.
        Yields a state dict that's available to all tools via context.
        """
        # Startup
        print(f"CBX MCP K8s Server v{__version__} starting...", file=sys.stderr)

        # Create session store based on configuration
        session_store = create_session_store(
            persistence=config.session.persistence.value,
            ttl_seconds=config.session.ttl_seconds,
            redis_url=config.session.redis_url,
        )

        # Start session store (for background cleanup tasks)
        if hasattr(session_store, "start"):
            await session_store.start()
            print(
                f"Session store started (persistence={config.session.persistence.value})",
                file=sys.stderr,
            )

        # Connect event store if using Redis
        if event_store and hasattr(event_store, "connect"):
            await event_store.connect()
            print(
                f"Event store connected (persistence={config.event_store.persistence.value})",
                file=sys.stderr,
            )

        # Create state available to tools
        state = {
            "config": config,
            "metrics": metrics,
            "tool_registry": tool_registry,
            "session_store": session_store,
            "event_store": event_store,
        }

        yield state

        # Shutdown
        print("CBX MCP K8s Server shutting down...", file=sys.stderr)

        # Disconnect event store
        if event_store and hasattr(event_store, "disconnect"):
            await event_store.disconnect()
            print("Event store disconnected", file=sys.stderr)

        # Stop session store cleanup task
        if hasattr(session_store, "stop"):
            await session_store.stop()
            print("Session store stopped", file=sys.stderr)

    # Create FastMCP instance
    # Note: host/port are passed to server.run() at startup time
    mcp = FastMCP(
        name="cbx_mcp_k8s",
        lifespan=lifespan,
    )

    # Add middleware for request preprocessing
    _register_middleware(mcp, config)

    # Register CLI tools discovered above
    if not skip_tool_validation:
        tool_registry.register_with_mcp(mcp)

    # Register built-in tools (ping for testing)
    _register_builtin_tools(mcp, config)

    # Register prompts
    _register_prompts(mcp)

    # Register cluster resources
    _register_resources(mcp)

    # Add custom HTTP routes for health and metrics
    _register_http_routes(mcp, metrics, lambda: registered_tools)

    return ServerBundle(server=mcp, event_store=event_store)


def create_server(
    config: K8sMCPServerConfig,
    tools_config_path: Path | None = None,
    skip_tool_validation: bool = False,
) -> ServerBundle:
    """
    Create and configure the MCP server (sync wrapper).

    Args:
        config: Server configuration
        tools_config_path: Optional path to tools.yaml config
        skip_tool_validation: Skip tool availability validation (for testing)

    Returns:
        ServerBundle containing FastMCP instance and event store

    Raises:
        RuntimeError: If required tools are not available
    """
    import asyncio

    return asyncio.run(
        create_server_async(config, tools_config_path, skip_tool_validation)
    )


def _register_http_routes(
    mcp: FastMCP,
    metrics: MetricsCollector,
    get_registered_tools: callable,
) -> None:
    """Register custom HTTP routes for health checks and metrics."""

    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        """Kubernetes liveness probe endpoint."""
        return JSONResponse({
            "status": "healthy",
            "version": __version__,
            "service": "cbx_mcp_k8s",
        })

    @mcp.custom_route("/ready", methods=["GET"])
    async def ready_check(request: Request) -> JSONResponse:
        """Kubernetes readiness probe endpoint."""
        tools = get_registered_tools()
        # Server is ready if it's running (tools are optional when skip_tool_validation=True)
        checks = {
            "server": True,
            "tools_registered": len(tools) > 0,
        }
        # Only the server check is required for readiness
        # tools_registered is informational
        is_ready = checks["server"]
        return JSONResponse(
            {
                "status": "ready" if is_ready else "not_ready",
                "checks": checks,
                "registered_tools": tools,
            },
            status_code=200 if is_ready else 503,
        )

    @mcp.custom_route("/metrics", methods=["GET"])
    async def metrics_endpoint(request: Request) -> PlainTextResponse:
        """Prometheus metrics endpoint."""
        return PlainTextResponse(
            metrics.format_prometheus(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )


def _register_builtin_tools(mcp: FastMCP, config: K8sMCPServerConfig) -> None:
    """
    Register built-in MCP tools.

    These are always-available tools that don't depend on external binaries.
    """

    @mcp.tool(
        name="k8s_ping",
        annotations={
            "title": "Ping",
            "readOnlyHint": True,
            "destructiveHint": False,
        },
    )
    async def k8s_ping() -> str:
        """
        Simple ping tool to verify server is responding.

        Returns:
            str: Pong response with server version
        """
        return f"pong from cbx_mcp_k8s v{__version__}"


def _register_prompts(mcp: FastMCP) -> None:
    """
    Register MCP prompts.

    Registers Kubernetes operation prompt templates that help LLMs
    generate appropriate kubectl, helm, and argocd commands.
    """
    from cbx_mcp_k8s.prompts import register_prompts

    register_prompts(mcp)


def _register_resources(mcp: FastMCP) -> None:
    """
    Register MCP resources.

    Registers Kubernetes cluster information resources that provide
    read-only access to cluster context, namespaces, and version info.
    """
    from cbx_mcp_k8s.resources import register_resources

    register_resources(mcp)


def _register_middleware(mcp: FastMCP, config: K8sMCPServerConfig) -> None:
    """
    Register MCP middleware for request processing.

    Args:
        mcp: FastMCP server instance
        config: Server configuration
    """
    from cbx_mcp_k8s.middleware import create_preprocessor

    # Create preprocessor middleware
    # Enable verbose logging in development
    verbose = config.server.log_level.lower() == "debug"
    preprocessor = create_preprocessor(verbose=verbose)

    # Register the middleware with FastMCP
    mcp.add_middleware(preprocessor)
    print(f"Registered ToolCallPreprocessor middleware (verbose={verbose})", file=sys.stderr)


