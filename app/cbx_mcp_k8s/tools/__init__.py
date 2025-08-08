# tools/__init__.py

from fastmcp import FastMCP, Context
from pydantic import Field


from ..executor import CommandHelpResult, CommandResult
from ..config import TOOLS_CONFIG

from .kubectl import kubectl_describe, kubectl_execute
from .helm import helm_describe, helm_execute
from .argocd import argocd_describe, argocd_execute
from ..utils import get_logger
logger = get_logger(__name__)


def register_tools(mcp: FastMCP, config: dict) -> None:
    """Register MCP tool functions with the MCP server."""

    # Register kubectl related tools
    if "kubectl" in TOOLS_CONFIG:
        @mcp.tool()
        async def describe_kubectl(
                command: str | None = Field(description="Specific kubectl command to get help for", default=None),
                ctx: Context | None = None,
        ) -> CommandHelpResult:
            """Get documentation and help text for kubectl commands."""
            return await kubectl_describe(command, ctx)

        @mcp.tool(description="Execute kubectl commands with support for Unix pipes.")
        async def execute_kubectl(
                command: str = Field(description="Complete kubectl command to execute (including any pipes and flags)"),
                timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)",
                                            default=None),
                ctx: Context | None = None,
        ) -> CommandResult:
            """Execute kubectl commands with support for Unix pipes."""
            return await kubectl_execute(command, timeout, ctx)

    # Register helm related tools
    if "helm" in TOOLS_CONFIG:
        @mcp.tool()
        async def describe_helm(
                command: str | None = Field(description="Specific Helm command to get help for", default=None),
                ctx: Context | None = None,
        ) -> CommandHelpResult:
            """Get documentation and help text for Helm commands."""
            return await helm_describe(command, ctx)

        @mcp.tool(description="Execute Helm commands with support for Unix pipes.")
        async def execute_helm(
                command: str = Field(description="Complete Helm command to execute (including any pipes and flags)"),
                timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)",
                                            default=None),
                ctx: Context | None = None,
        ) -> CommandResult:
            """Execute Helm commands with support for Unix pipes."""
            return await helm_execute(command, timeout, ctx)

    # Register argocd related tools
    if "argocd" in TOOLS_CONFIG:
        @mcp.tool()
        async def describe_argocd(
                command: str | None = Field(description="Specific ArgoCD command to get help for", default=None),
                ctx: Context | None = None,
        ) -> CommandHelpResult:
            """Get documentation and help text for ArgoCD commands."""
            return await argocd_describe(command, ctx)

        @mcp.tool(description="Execute ArgoCD commands with support for Unix pipes.")
        async def execute_argocd(
                command: str = Field(description="Complete ArgoCD command to execute (including any pipes and flags)"),
                timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)",
                                            default=None),
                ctx: Context | None = None,
        ) -> CommandResult:
            """Execute ArgoCD commands with support for Unix pipes."""
            return await argocd_execute(command, timeout, ctx)
