#!/usr/bin/env python3

import sys
import argparse
import os
import signal
import threading
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


from cbx_mcp_k8s.utils import setup_logging, get_logger
# Setup logging
setup_logging(level=os.getenv("CBX_LOG_LEVEL", "INFO"))

from cbx_mcp_k8s import create_server
# Global variables for signal handling
_server_instance = None
_config_dir = None
_config_lock = threading.Lock()


def parse_arguments():
    """Parse command line arguments and environment variables."""
    parser = argparse.ArgumentParser(
        description="CBX MCP Server for Kubernetes",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Priority order for config directory:
    # 1. Default: $HOME/.k8smcp
    # 2. Environment variable: CBX_MCP_CONFIG_DIR
    # 3. Command line argument: --config-dir (highest priority)

    home_dir = os.path.expanduser("~")
    default_config_dir = os.path.join(home_dir, ".k8smcp")

    # Override with environment variable if set
    env_config_dir = os.getenv("CBX_MCP_CONFIG_DIR")
    if env_config_dir:
        default_config_dir = env_config_dir

    parser.add_argument(
        "--config-dir",
        type=str,
        default=default_config_dir,
        help=f"Directory containing config.yaml file. "
             f"Default: $HOME/.k8smcp, overridden by CBX_MCP_CONFIG_DIR env var if set. "
             f"Current default: {default_config_dir}"
    )

    return parser.parse_args()


def safe_reinitialize_configs(config_dir):
    """Thread-safe configuration reinitialization with validation."""
    logger = get_logger(__name__)

    with _config_lock:
        try:
            logger.info(f"Reloading configuration from: {config_dir}")

            # Import here to avoid circular imports during signal handling
            from cbx_mcp_k8s.config import reinitialize_configs

            # This will validate and load the config in one step
            reinitialize_configs(config_dir)

            logger.info("Configuration reloaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            logger.error(f"Keeping existing configuration")
            return False


def setup_signal_handlers():
    """Setup signal handlers for config reloading only.

    Note: SIGINT/SIGTERM are handled by FastMCP's built-in mechanisms.
    We only handle SIGHUP for config reload functionality.
    """
    logger = get_logger(__name__)

    def handle_sighup(signum, frame):
        """Handle SIGHUP - reload configuration"""
        logger.info("Received SIGHUP signal - reloading configuration...")

        config_dir = _config_dir or os.getenv('CBX_MCP_CONFIG_DIR')
        if config_dir:
            success = safe_reinitialize_configs(config_dir)
            if success:
                logger.info("Configuration reload completed successfully")
                logger.info("Note: Some changes may require server restart to take full effect")
            else:
                logger.warning("Configuration reload failed - server continues with existing config")
        else:
            logger.warning("No config directory available - cannot reload configuration")
            logger.info("Set CBX_MCP_CONFIG_DIR environment variable or use --config-dir argument")

    # Only register SIGHUP - let FastMCP handle SIGINT/SIGTERM
    signal.signal(signal.SIGHUP, handle_sighup)

    logger.info("Signal handlers registered:")
    logger.info("  SIGHUP: Configuration reload")
    logger.info("  SIGINT/SIGTERM: Handled by FastMCP (use Ctrl+C to stop)")


def initialize_configuration(args):
    """Initialize configuration based on CLI arguments and environment."""
    global _config_dir
    logger = get_logger(__name__)

    _config_dir = args.config_dir

    # ALWAYS refresh the global configuration
    from cbx_mcp_k8s.config import reinitialize_configs
    reinitialize_configs(args.config_dir)

    logger.info("Configuration initialization complete")


def run_server():
    """Run the MCP server with appropriate transport."""
    global _server_instance
    logger = get_logger(__name__)

    try:
        logger.info("Initializing CBX MCP Server for K8S...")

        # Create server - it will use the refreshed global configs
        _server_instance = create_server()

        # Get server configuration from the refreshed global config
        from cbx_mcp_k8s.config import MCP_CONFIG
        server_config = MCP_CONFIG.get('server', {})
        transport_type = server_config.get('transport_type', 'stdio')

        if transport_type == "stdio":
            logger.info("Running CBX MCP Server for K8S with STDIO transport...")
            logger.info("Server ready - use Ctrl+C to stop, kill -HUP <pid> to reload config")
            _server_instance.run(transport="stdio")

        elif transport_type in ["http", "streamable-http"]:
            host = server_config.get('host', '127.0.0.1')
            port = server_config.get('port', 8080)
            path = server_config.get('path', '/mcp')
            log_level = server_config.get('log_level', 'INFO')

            logger.info(f"Running CBX MCP Server for K8S with HTTP transport...")
            logger.info(f"Server will be available at: http://{host}:{port}{path}")
            logger.info("Server ready - use Ctrl+C to stop, kill -HUP <pid> to reload config")

            _server_instance.run(
                transport=transport_type,
                host=host,
                port=port,
                path=path,
                log_level=log_level
            )
        else:
            raise ValueError(f"Unsupported transport type: {transport_type}. Only 'stdio' and 'http' are supported.")

    except Exception as e:
        logger.error(f"Server error: {e}")
        logger.error(f"Error type: {type(e).__name__}")

        # Debug information for development
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")

        # Only drop into debugger in development (not in production)
        if os.getenv('CBX_DEBUG_MODE', '').lower() in ('true', '1', 'yes'):
            import pdb
            pdb.post_mortem()

        raise


def main():
    """Main application entry point with signal handling and config reload support."""
    logger = get_logger(__name__)

    try:
        # Parse command line arguments
        args = parse_arguments()

        # Setup signal handlers before starting server
        setup_signal_handlers()

        # Initialize configuration
        initialize_configuration(args)

        # Run the server
        run_server()

    except KeyboardInterrupt:
        # This handles both direct Ctrl+C and signal-based interrupts
        logger.info("Keyboard interrupt received - shutting down...")

    except SystemExit:
        # Handle explicit sys.exit() calls
        logger.info("System exit requested - shutting down...")

    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")

        # Debug information for development
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")

        # Only drop into debugger in development
        if os.getenv('CBX_DEBUG_MODE', '').lower() in ('true', '1', 'yes'):
            import pdb
            pdb.post_mortem()

        return 1

    finally:
        # Cleanup
        logger.info("Performing cleanup...")

        # Additional cleanup if needed
        if _server_instance:
            try:
                # If your server has a cleanup method, call it here
                # _server_instance.cleanup()
                pass
            except Exception as e:
                logger.warning(f"Error during server cleanup: {e}")

        logger.info("Server shutdown complete")
        return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
        sys.exit(0)
    except Exception:
        sys.exit(1)

