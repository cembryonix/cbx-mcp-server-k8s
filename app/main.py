#!/usr/bin/env python3
"""
CBX MCP K8s Server - Entry Point

This is the main entry point for the MCP server.
Supports both stdio and streamable-http transports.
"""

import argparse
import signal
import sys
from pathlib import Path

# Add app directory to path for imports when running directly
APP_DIR = Path(__file__).parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from cbx_mcp_k8s import __version__
from cbx_mcp_k8s.config import load_config
from cbx_mcp_k8s.server import ServerBundle, create_server


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="CBX MCP Server for Kubernetes Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with stdio transport (default for local dev)
  python main.py --transport stdio

  # Start with HTTP transport
  python main.py --transport streamable-http --port 8080

  # Use custom config directory
  python main.py --config-dir /path/to/config
        """,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"cbx-mcp-k8s {__version__}",
    )
    parser.add_argument(
        "--config-dir",
        type=str,
        help="Configuration directory path (default: ~/.k8smcp/)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        help="Transport protocol (overrides config)",
    )
    parser.add_argument(
        "--host",
        type=str,
        help="Host to bind to (for HTTP transport, overrides config)",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port to listen on (for HTTP transport, overrides config)",
    )
    parser.add_argument(
        "--skip-tool-validation",
        action="store_true",
        help="Skip tool availability validation (for testing without kubectl/helm/argocd)",
    )
    return parser.parse_args()


def setup_signal_handlers(config_dir: str | None) -> None:
    """Setup signal handlers for graceful shutdown and config reload."""

    def handle_sighup(signum, frame):
        """Handle SIGHUP for config reload."""
        print("Received SIGHUP, config reload not yet implemented", file=sys.stderr)
        # TODO: Implement config reload when server supports it

    # Only setup SIGHUP on Unix systems
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, handle_sighup)


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Load configuration
    try:
        config = load_config(args.config_dir)
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        return 1

    # Apply CLI overrides
    if args.transport:
        config.server.transport = args.transport
    if args.host:
        config.server.host = args.host
    if args.port:
        config.server.port = args.port

    # Setup signal handlers
    setup_signal_handlers(args.config_dir)

    # Create and run server
    try:
        bundle = create_server(
            config,
            skip_tool_validation=args.skip_tool_validation,
        )

        print(f"Starting CBX MCP K8s Server v{__version__}", file=sys.stderr)
        print(f"Transport: {config.server.transport}", file=sys.stderr)

        if config.server.transport == "stdio":
            print("Running in stdio mode...", file=sys.stderr)
            bundle.server.run(transport="stdio")
        else:
            print(
                f"Running on http://{config.server.host}:{config.server.port}",
                file=sys.stderr,
            )

            # For HTTP transport, we need to use http_app() to pass event_store
            # This enables session resumability after pod restarts
            if bundle.event_store:
                print(
                    f"Event store enabled for session resumability",
                    file=sys.stderr,
                )
                # Create ASGI app with event store and run with uvicorn
                import uvicorn

                app = bundle.server.http_app(event_store=bundle.event_store)
                uvicorn.run(
                    app,
                    host=config.server.host,
                    port=config.server.port,
                    log_level="info",
                )
            else:
                # No event store, use default run method
                bundle.server.run(
                    transport="streamable-http",
                    host=config.server.host,
                    port=config.server.port,
                )
    except KeyboardInterrupt:
        print("\nShutting down...", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
