# cbx_mcp_k8s/server.py

from fastmcp import Context, FastMCP

from .config import INSTRUCTIONS, MCP_CONFIG

from.version import __version__
from .tools import register_tools
from .prompts import register_prompts
from .resources import register_resources

from .utils import get_logger

logger = get_logger(__name__)

def create_server() -> FastMCP:
    """Create and configure the FastMCP server instance."""

    instructions = INSTRUCTIONS
    config = MCP_CONFIG

    # Create the FastMCP server
    logger.info("Creating FastMCP server")
    mcp = FastMCP(
        name=config.get("server_name", "cbx_mcp_k8s"),
        instructions=instructions,
        version=__version__
    )

    # Register prompts
    logger.info("Registering prompts")
    register_prompts(mcp)

    # Register all tool functions
    logger.info("Registering tools")
    register_tools(mcp, config)

    # Register resources
    logger.info("Registering resources")
    register_resources(mcp,config)
    return mcp
