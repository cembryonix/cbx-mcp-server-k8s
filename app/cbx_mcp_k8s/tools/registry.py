"""
Tool Registry.

Handles loading tool configuration, creating tool instances,
verifying availability, and registering tools with FastMCP.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

from cbx_mcp_k8s.tools.base import (
    BaseTool,
    CliTool,
    PythonTool,
    ToolCheckResult,
    ToolConfig,
    ToolType,
)


@dataclass
class ToolRegistrationResult:
    """Result of tool registration process."""

    tool_name: str
    registered: bool
    message: str
    check_result: ToolCheckResult | None = None


@dataclass
class RegistryResult:
    """Result of the full registration process."""

    success: bool
    registered_tools: list[str]
    failed_required: list[str]
    skipped_optional: list[str]
    results: list[ToolRegistrationResult] = field(default_factory=list)

    def summary(self) -> str:
        """Generate summary message."""
        lines = [
            f"Tool Registration: {'SUCCESS' if self.success else 'FAILED'}",
            f"  Registered: {len(self.registered_tools)}",
        ]
        if self.registered_tools:
            for name in self.registered_tools:
                lines.append(f"    - {name}")

        if self.failed_required:
            lines.append(f"  Failed (required): {len(self.failed_required)}")
            for name in self.failed_required:
                lines.append(f"    - {name}")

        if self.skipped_optional:
            lines.append(f"  Skipped (optional): {len(self.skipped_optional)}")
            for name in self.skipped_optional:
                lines.append(f"    - {name}")

        return "\n".join(lines)


class ToolRegistry:
    """
    Manages tool discovery, validation, and registration.

    Loads tool configuration, creates tool instances, verifies
    availability, and registers tools with FastMCP server.
    """

    def __init__(self, executor_config: Any):
        """
        Initialize registry.

        Args:
            executor_config: Configuration for command execution
        """
        self.executor_config = executor_config
        self._tools: dict[str, BaseTool] = {}
        self._cli_config: dict[str, dict] = {}
        self._python_config: dict[str, dict] = {}

    def load_config(self, config_path: Path | None = None) -> None:
        """
        Load tool configuration from YAML.

        Args:
            config_path: Path to tools.yaml. If None, uses default.
        """
        if config_path is None:
            # Use default config
            config_path = (
                Path(__file__).parent.parent / "config" / "defaults" / "tools.yaml"
            )

        if not config_path.exists():
            print(f"Warning: Tools config not found at {config_path}", file=sys.stderr)
            return

        with open(config_path) as f:
            config = yaml.safe_load(f)

        self._cli_config = config.get("cli_tools", {}) or {}
        self._python_config = config.get("python_tools", {}) or {}

    def _create_tool_config(
        self, name: str, tool_type: ToolType, config_dict: dict
    ) -> ToolConfig:
        """Create ToolConfig from dictionary."""
        return ToolConfig(
            name=name,
            tool_type=tool_type,
            required=config_dict.get("required", False),
            check_cmd=config_dict.get("check_cmd", ""),
            test_cmd=config_dict.get("test_cmd", ""),
            help_flag=config_dict.get("help_flag", "--help"),
            description=config_dict.get("description", ""),
            example=config_dict.get("example", ""),
            parameters=config_dict.get("parameters", {}),
        )

    async def discover_and_validate(
        self, skip_connectivity_test: bool = False
    ) -> RegistryResult:
        """
        Discover available tools and validate them.

        Args:
            skip_connectivity_test: If True, skip test_cmd validation

        Returns:
            RegistryResult with registration status
        """
        registered = []
        failed_required = []
        skipped_optional = []
        results = []

        # Process CLI tools
        for name, config_dict in self._cli_config.items():
            tool_config = self._create_tool_config(name, ToolType.CLI, config_dict)
            tool = CliTool(tool_config, self.executor_config)

            result = await self._validate_and_register_tool(
                tool, skip_connectivity_test
            )
            results.append(result)

            if result.registered:
                registered.append(name)
                self._tools[name] = tool
            elif tool.is_required:
                failed_required.append(name)
            else:
                skipped_optional.append(name)

        # Process Python tools
        for name, config_dict in self._python_config.items():
            tool_config = self._create_tool_config(name, ToolType.PYTHON, config_dict)
            tool = PythonTool(tool_config)

            result = await self._validate_and_register_tool(
                tool, skip_connectivity_test
            )
            results.append(result)

            if result.registered:
                registered.append(name)
                self._tools[name] = tool
            elif tool.is_required:
                failed_required.append(name)
            else:
                skipped_optional.append(name)

        return RegistryResult(
            success=len(failed_required) == 0,
            registered_tools=registered,
            failed_required=failed_required,
            skipped_optional=skipped_optional,
            results=results,
        )

    async def _validate_and_register_tool(
        self, tool: BaseTool, skip_connectivity_test: bool
    ) -> ToolRegistrationResult:
        """Validate a single tool."""
        # Check availability
        check_result = await tool.check_available()

        if not check_result.available:
            return ToolRegistrationResult(
                tool_name=tool.name,
                registered=False,
                message=check_result.message,
                check_result=check_result,
            )

        # Optionally test connectivity
        if not skip_connectivity_test and tool.config.test_cmd:
            conn_result = await tool.test_connectivity()
            if not conn_result.available:
                # Log warning but don't fail registration
                print(
                    f"Warning: {tool.name} connectivity test failed: {conn_result.message}",
                    file=sys.stderr,
                )

        return ToolRegistrationResult(
            tool_name=tool.name,
            registered=True,
            message=f"{tool.name} registered successfully",
            check_result=check_result,
        )

    def register_with_mcp(self, mcp: FastMCP) -> None:
        """
        Register all validated tools with FastMCP server.

        Args:
            mcp: FastMCP server instance
        """
        for tool in self._tools.values():
            self._register_tool_handlers(mcp, tool)

    def _register_tool_handlers(self, mcp: FastMCP, tool: BaseTool) -> None:
        """Register execute and describe handlers for a tool."""
        if tool.tool_type == ToolType.CLI:
            self._register_cli_tool(mcp, tool)
        else:
            self._register_python_tool(mcp, tool)

    def _register_cli_tool(self, mcp: FastMCP, tool: CliTool) -> None:
        """Register CLI tool execute and describe handlers."""
        execute_name = tool.get_mcp_tool_name("execute")
        describe_name = tool.get_mcp_tool_name("describe")

        # Capture tool in closure
        captured_tool = tool

        # Register execute tool
        @mcp.tool(
            name=execute_name,
            annotations={
                "title": f"Execute {tool.name} Command",
                "readOnlyHint": False,
                "destructiveHint": True,
                "openWorldHint": True,
            },
        )
        async def cli_execute(
            command: str,
            timeout: int | None = None,
        ) -> str:
            f"""
            Execute a {captured_tool.name} command.

            Args:
                command: Full {captured_tool.name} command to execute
                timeout: Optional timeout in seconds

            Returns:
                Command output or error message
            """
            result = await captured_tool.execute(command=command, timeout=timeout)

            if result.success:
                return result.stdout
            else:
                return f"Error (exit code {result.exit_code}): {result.stderr or result.stdout}"

        # Register describe tool
        @mcp.tool(
            name=describe_name,
            annotations={
                "title": f"Describe {tool.name}",
                "readOnlyHint": True,
                "destructiveHint": False,
            },
        )
        async def cli_describe() -> str:
            f"""
            Get help information for {captured_tool.name}.

            Returns:
                Help text for the tool
            """
            return await captured_tool.describe()

    def _register_python_tool(self, mcp: FastMCP, tool: PythonTool) -> None:
        """Register Python tool execute and describe handlers."""
        execute_name = tool.get_mcp_tool_name("execute")
        describe_name = tool.get_mcp_tool_name("describe")

        # Capture tool in closure
        captured_tool = tool

        # For Python tools, we need to dynamically create the function
        # based on the parameter schema
        # This is a simplified version - full implementation would
        # generate proper function signatures

        @mcp.tool(
            name=execute_name,
            annotations={
                "title": f"Execute {tool.name}",
                "readOnlyHint": True,  # Python tools are typically read-only
                "destructiveHint": False,
            },
        )
        async def python_execute(**kwargs) -> str:
            f"""
            Execute {captured_tool.name} with JSON parameters.

            Returns:
                Execution result
            """
            result = await captured_tool.execute(**kwargs)

            if result.success:
                return result.stdout
            else:
                return f"Error: {result.stderr or result.stdout}"

        @mcp.tool(
            name=describe_name,
            annotations={
                "title": f"Describe {tool.name}",
                "readOnlyHint": True,
                "destructiveHint": False,
            },
        )
        async def python_describe() -> str:
            f"""
            Get help information for {captured_tool.name}.

            Returns:
                Help text for the tool
            """
            return await captured_tool.describe()

    def get_tool(self, name: str) -> BaseTool | None:
        """Get a registered tool by name."""
        return self._tools.get(name)

    def get_all_tools(self) -> list[BaseTool]:
        """Get all registered tools."""
        return list(self._tools.values())

    @property
    def tool_names(self) -> list[str]:
        """Get names of all registered tools."""
        return list(self._tools.keys())


async def create_and_register_tools(
    mcp: FastMCP,
    executor_config: Any,
    tools_config_path: Path | None = None,
    skip_connectivity_test: bool = False,
) -> RegistryResult:
    """
    Convenience function to create registry and register tools.

    Args:
        mcp: FastMCP server instance
        executor_config: Executor configuration
        tools_config_path: Optional path to tools.yaml
        skip_connectivity_test: Skip connectivity tests

    Returns:
        RegistryResult with registration status

    Raises:
        RuntimeError: If required tools are not available
    """
    registry = ToolRegistry(executor_config)
    registry.load_config(tools_config_path)

    result = await registry.discover_and_validate(skip_connectivity_test)

    if not result.success:
        raise RuntimeError(
            f"Required tools not available: {result.failed_required}\n"
            f"{result.summary()}"
        )

    registry.register_with_mcp(mcp)

    return result
