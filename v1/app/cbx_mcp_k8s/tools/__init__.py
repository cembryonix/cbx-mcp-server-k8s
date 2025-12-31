# tools/__init__.py
"""
Dynamic tool registration for CLI tools.
Tools are registered based on TOOLS_CONFIG - no code changes needed to add new tools.
"""

from fastmcp import FastMCP, Context
from pydantic import Field

from ..executor import CommandHelpResult, CommandResult
from ..config import TOOLS_CONFIG
from .cli_tools import cli_describe, cli_execute, get_tool_display_name
from ..utils import get_logger

logger = get_logger(__name__)


def register_tools(mcp: FastMCP, config: dict) -> None:
    """
    Dynamically register MCP tool functions for all configured CLI tools.

    Tools are registered based on TOOLS_CONFIG. To add a new tool:
    1. Add entry to supported_cli_tools.json
    2. Add security rules to default_security_config.yaml (optional)

    No code changes required!
    """

    for tool_name in TOOLS_CONFIG:
        tool_config = TOOLS_CONFIG[tool_name]
        display_name = get_tool_display_name(tool_name)

        logger.debug(f"Registering tools for: {tool_name}")

        # Register describe tool
        _register_describe_tool(mcp, tool_name, display_name)

        # Register execute tool
        _register_execute_tool(mcp, tool_name, display_name)


def _register_describe_tool(mcp: FastMCP, tool_name: str, display_name: str) -> None:
    """Register a describe_<tool> function for the given CLI tool."""

    # Create a closure that captures tool_name
    async def describe_func(
        command: str | None = Field(
            description=f"Specific {display_name} command to get help for",
            default=None
        ),
        ctx: Context | None = None,
    ) -> CommandHelpResult:
        return await cli_describe(tool_name, command, ctx)

    # Set function metadata for MCP registration
    describe_func.__name__ = f"describe_{tool_name}"
    describe_func.__doc__ = f"Get documentation and help text for {display_name} commands."

    # Register with MCP - describe tools are read-only (no side effects)
    mcp.tool(annotations={"readOnlyHint": True})(describe_func)


def _register_execute_tool(mcp: FastMCP, tool_name: str, display_name: str) -> None:
    """Register an execute_<tool> function for the given CLI tool."""

    # Create a closure that captures tool_name
    async def execute_func(
        command: str = Field(
            description=f"Complete {display_name} command to execute (including any pipes and flags)"
        ),
        timeout: int | None = Field(
            description="Maximum execution time in seconds (default: 300)",
            default=None
        ),
        ctx: Context | None = None,
    ) -> CommandResult:
        return await cli_execute(tool_name, command, timeout, ctx)

    # Set function metadata for MCP registration
    execute_func.__name__ = f"execute_{tool_name}"
    execute_func.__doc__ = f"Execute {display_name} commands with support for Unix pipes."

    # Register with MCP - execute tools can modify cluster state (destructive)
    mcp.tool(
        description=f"Execute {display_name} commands with support for Unix pipes.",
        annotations={"destructiveHint": True, "openWorldHint": True}
    )(execute_func)