# tools/kubectl.py

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

async def kubectl_describe(
    command: str | None,
    ctx: Context | None,
) -> CommandHelpResult:
    """Get documentation and help text for kubectl commands."""
    logger.info(f"Getting kubectl documentation for command: {command or 'None'}")

    help_flag_str = TOOLS_CONFIG.get("kubectl", {}).get("help_flag")

    try:
        if ctx:
            await ctx.info(f"Fetching kubectl help for {command or 'general usage'}")

        result = await get_command_help("kubectl", help_flag_str, command)
        if ctx and result.status == "error":
            await ctx.error(f"Error retrieving kubectl help: {result.help_text}")
        return result
    except Exception as e:
        logger.error(f"Error in describe_kubectl: {e}")
        if ctx:
            await ctx.error(f"Unexpected error retrieving kubectl help: {str(e)}")
        return CommandHelpResult(
            help_text=f"Error retrieving kubectl help: {str(e)}",
            status="error",
            error={"message": str(e), "code": "INTERNAL_ERROR"}
        )


async def kubectl_execute(
    command: str,
    timeout: int | None,
    ctx: Context | None,
) -> CommandResult:
    """Execute kubectl commands with support for Unix pipes."""

    return await execute_tool_command("kubectl", command, timeout, ctx )