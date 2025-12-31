# tools/cli_tools.py
"""
Consolidated CLI tool module for dynamic tool registration.
Provides parameterized functions that work with any CLI tool defined in TOOLS_CONFIG.
"""

from fastmcp import Context
from fastmcp.exceptions import ToolError

from ..config import TOOLS_CONFIG
from ..executor import (
    get_command_help,
    execute_tool_command,
    CommandHelpResult,
    CommandResult
)
from ..utils import get_logger

logger = get_logger(__name__)


async def cli_describe(
    tool_name: str,
    command: str | None,
    ctx: Context | None,
) -> CommandHelpResult:
    """
    Get documentation and help text for any CLI tool command.

    Args:
        tool_name: Name of the CLI tool (e.g., 'kubectl', 'helm', 'argocd')
        command: Specific command to get help for (optional)
        ctx: FastMCP context for logging

    Returns:
        CommandHelpResult with help text or error information
    """
    display_name = tool_name.title() if tool_name != "argocd" else "ArgoCD"
    logger.info(f"Getting {display_name} documentation for command: {command or 'None'}")

    help_flag_str = TOOLS_CONFIG.get(tool_name, {}).get("help_flag")

    try:
        if ctx:
            await ctx.info(f"Fetching {display_name} help for {command or 'general usage'}")

        result = await get_command_help(tool_name, help_flag_str, command)

        # Raise ToolError for error results so MCP returns isError: true
        if result.status == "error":
            if ctx:
                await ctx.error(f"Error retrieving {display_name} help: {result.help_text}")
            raise ToolError(result.help_text)

        return result
    except ToolError:
        # Re-raise ToolError as-is
        raise
    except Exception as e:
        logger.error(f"Error in describe_{tool_name}: {e}")
        if ctx:
            await ctx.error(f"Unexpected error retrieving {display_name} help: {str(e)}")
        raise ToolError(f"Error retrieving {display_name} help: {str(e)}")


async def cli_execute(
    tool_name: str,
    command: str,
    timeout: int | None,
    ctx: Context | None,
) -> CommandResult:
    """
    Execute any CLI tool command with support for Unix pipes.

    Args:
        tool_name: Name of the CLI tool (e.g., 'kubectl', 'helm', 'argocd')
        command: Complete command to execute (including any pipes and flags)
        timeout: Maximum execution time in seconds (optional)
        ctx: FastMCP context for logging

    Returns:
        CommandResult with output or error information

    Raises:
        ToolError: When command execution fails (ensures MCP isError: true)
    """
    result = await execute_tool_command(tool_name, command, timeout, ctx)

    # Raise ToolError for error results so MCP returns isError: true
    if result.get("status") == "error":
        error_msg = result.get("output") or result.get("error", {}).get("message", "Command execution failed")
        raise ToolError(error_msg)

    return result


def get_tool_display_name(tool_name: str) -> str:
    """Get display-friendly name for a tool."""
    special_names = {
        "argocd": "ArgoCD",
        "kubectl": "kubectl",
        "helm": "Helm",
    }
    return special_names.get(tool_name, tool_name.title())