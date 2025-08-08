# tools/helm.py

from fastmcp import Context

from ..config import TOOLS_CONFIG
from ..executor import (
    get_command_help,
    execute_tool_command,
    CommandHelpResult,
    CommandResult
)
from ..utils import get_logger

logger = get_logger(__name__)

async def helm_describe(
    command: str | None,
    ctx: Context | None
) -> CommandHelpResult:
    """Get documentation and help text for Helm commands."""
    logger.info(f"Getting Helm documentation for command: {command or 'None'}")

    help_flag_str = TOOLS_CONFIG.get("helm", {}).get("help_flag")

    try:
        if ctx:
            await ctx.info(f"Fetching Helm help for {command or 'general usage'}")

        result = await get_command_help("helm", help_flag_str, command)
        if ctx and result.status == "error":
            await ctx.error(f"Error retrieving Helm help: {result.help_text}")
        return result
    except Exception as e:
        logger.error(f"Error in describe_helm: {e}")
        if ctx:
            await ctx.error(f"Unexpected error retrieving Helm help: {str(e)}")
        return CommandHelpResult(
            help_text=f"Error retrieving Helm help: {str(e)}",
            status="error",
            error={"message": str(e), "code": "INTERNAL_ERROR"}
        )


async def helm_execute(
        command: str,
        timeout: int | None,
        ctx: Context | None
) -> CommandResult:
    """Execute Helm commands with support for Unix pipes."""

    return await execute_tool_command("helm", command, timeout, ctx)