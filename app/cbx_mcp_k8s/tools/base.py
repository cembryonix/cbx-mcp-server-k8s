"""
Base tool classes and interfaces.

Defines the abstract interface for all tools (CLI and Python)
and provides concrete implementations for each type.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from cbx_mcp_k8s.executor.types import CommandResult


class ToolType(str, Enum):
    """Type of tool implementation."""

    CLI = "cli"  # External binary via subprocess (kubectl, helm)
    PYTHON = "python"  # Python-native, part of this package


@dataclass
class ToolConfig:
    """Configuration for a tool."""

    name: str
    tool_type: ToolType
    required: bool
    check_cmd: str
    test_cmd: str
    help_flag: str
    description: str
    example: str
    # For Python tools - parameter schema for JSON input
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCheckResult:
    """Result of checking tool availability."""

    available: bool
    message: str
    version: str | None = None


class BaseTool(ABC):
    """
    Base interface for all tools.

    Both CLI and Python tools implement this interface,
    allowing uniform registration and invocation.
    """

    def __init__(self, config: ToolConfig):
        self.config = config

    @property
    def name(self) -> str:
        """Tool name (e.g., 'kubectl', 'eksinfo')."""
        return self.config.name

    @property
    def tool_type(self) -> ToolType:
        """Tool type (CLI or Python)."""
        return self.config.tool_type

    @property
    def description(self) -> str:
        """Tool description for MCP."""
        return self.config.description

    @property
    def is_required(self) -> bool:
        """Whether this tool is required for server startup."""
        return self.config.required

    @abstractmethod
    async def check_available(self) -> ToolCheckResult:
        """
        Check if tool is available and functioning.

        For CLI tools: runs check_cmd to verify binary exists
        For Python tools: runs check_cmd to verify module/credentials

        Returns:
            ToolCheckResult with availability status
        """
        pass

    @abstractmethod
    async def test_connectivity(self) -> ToolCheckResult:
        """
        Test that tool can connect to its backend.

        For CLI tools: runs test_cmd (e.g., kubectl auth can-i)
        For Python tools: runs test_cmd to verify credentials

        Returns:
            ToolCheckResult with connectivity status
        """
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> CommandResult:
        """
        Execute the tool.

        For CLI tools: kwargs contains 'command' string
        For Python tools: kwargs contains JSON parameters

        Returns:
            CommandResult with execution output
        """
        pass

    @abstractmethod
    async def describe(self) -> str:
        """
        Get tool help/description.

        Returns help text for the tool.
        """
        pass

    def get_mcp_tool_name(self, action: str) -> str:
        """
        Get MCP tool name for this tool.

        Args:
            action: 'execute' or 'describe'

        Returns:
            MCP tool name (e.g., 'k8s_kubectl_execute')
        """
        return f"k8s_{self.name}_{action}"


class CliTool(BaseTool):
    """
    CLI tool implementation.

    Executes external binaries (kubectl, helm, argocd) via subprocess.
    Commands go through security validation before execution.
    """

    def __init__(self, config: ToolConfig, executor_config: Any):
        """
        Initialize CLI tool.

        Args:
            config: Tool configuration
            executor_config: Executor configuration for timeouts, etc.
        """
        super().__init__(config)
        self.executor_config = executor_config

    async def check_available(self) -> ToolCheckResult:
        """Check if CLI binary is available."""
        from cbx_mcp_k8s.executor.runner import execute_command

        try:
            result = await execute_command(
                command=self.config.check_cmd,
                timeout=10,
                security_config=None,  # Skip security for check commands
            )

            if result.success:
                # Try to extract version from output
                version = result.stdout.strip()[:100] if result.stdout else None
                return ToolCheckResult(
                    available=True,
                    message=f"{self.name} is available",
                    version=version,
                )
            else:
                return ToolCheckResult(
                    available=False,
                    message=f"{self.name} check failed: {result.stderr or result.stdout}",
                )

        except FileNotFoundError:
            return ToolCheckResult(
                available=False,
                message=f"{self.name} binary not found",
            )
        except Exception as e:
            return ToolCheckResult(
                available=False,
                message=f"{self.name} check error: {e}",
            )

    async def test_connectivity(self) -> ToolCheckResult:
        """Test CLI tool connectivity (e.g., k8s auth)."""
        from cbx_mcp_k8s.executor.runner import execute_command

        try:
            result = await execute_command(
                command=self.config.test_cmd,
                timeout=30,
                security_config=None,  # Skip security for test commands
            )

            if result.success:
                return ToolCheckResult(
                    available=True,
                    message=f"{self.name} connectivity OK",
                )
            else:
                return ToolCheckResult(
                    available=False,
                    message=f"{self.name} connectivity failed: {result.stderr or result.stdout}",
                )

        except Exception as e:
            return ToolCheckResult(
                available=False,
                message=f"{self.name} connectivity error: {e}",
            )

    async def execute(self, command: str, timeout: int | None = None) -> CommandResult:
        """
        Execute CLI command.

        Args:
            command: Command string (e.g., "get pods" or "kubectl get pods")
            timeout: Optional timeout override

        Returns:
            CommandResult with execution output
        """
        from cbx_mcp_k8s.executor.runner import execute_command

        actual_timeout = timeout or self.executor_config.default_timeout

        # Add tool prefix if not present (LLMs often omit it)
        if not command.strip().startswith(self.name):
            command = f"{self.name} {command}"

        return await execute_command(
            command=command,
            timeout=actual_timeout,
            security_config=self.executor_config.security_config,
        )

    async def describe(self) -> str:
        """Get CLI tool help."""
        from cbx_mcp_k8s.executor.runner import execute_command

        help_cmd = f"{self.name} {self.config.help_flag}"

        result = await execute_command(
            command=help_cmd,
            timeout=10,
            security_config=None,
        )

        if result.success:
            return result.stdout
        else:
            return f"Error getting help: {result.stderr or result.stdout}"


class PythonTool(BaseTool):
    """
    Python tool implementation.

    Executes Python code directly (no subprocess for main execution).
    Does NOT go through security validation (trusted internal code).
    Accepts JSON parameters instead of command string.
    """

    def __init__(self, config: ToolConfig, module: Any = None):
        """
        Initialize Python tool.

        Args:
            config: Tool configuration
            module: Python module implementing the tool (optional, loaded later)
        """
        super().__init__(config)
        self._module = module

    async def check_available(self) -> ToolCheckResult:
        """Check if Python tool is available."""
        from cbx_mcp_k8s.executor.runner import execute_command

        try:
            # Use check_cmd like CLI tools (e.g., "eksinfo --version")
            result = await execute_command(
                command=self.config.check_cmd,
                timeout=10,
                security_config=None,
            )

            if result.success:
                version = result.stdout.strip()[:100] if result.stdout else None
                return ToolCheckResult(
                    available=True,
                    message=f"{self.name} is available",
                    version=version,
                )
            else:
                return ToolCheckResult(
                    available=False,
                    message=f"{self.name} check failed: {result.stderr or result.stdout}",
                )

        except Exception as e:
            return ToolCheckResult(
                available=False,
                message=f"{self.name} check error: {e}",
            )

    async def test_connectivity(self) -> ToolCheckResult:
        """Test Python tool connectivity (e.g., AWS credentials)."""
        from cbx_mcp_k8s.executor.runner import execute_command

        try:
            result = await execute_command(
                command=self.config.test_cmd,
                timeout=30,
                security_config=None,
            )

            if result.success:
                return ToolCheckResult(
                    available=True,
                    message=f"{self.name} connectivity OK",
                )
            else:
                return ToolCheckResult(
                    available=False,
                    message=f"{self.name} connectivity failed: {result.stderr or result.stdout}",
                )

        except Exception as e:
            return ToolCheckResult(
                available=False,
                message=f"{self.name} connectivity error: {e}",
            )

    async def execute(self, **kwargs) -> CommandResult:
        """
        Execute Python tool with JSON parameters.

        Args:
            **kwargs: JSON parameters defined in tool config

        Returns:
            CommandResult with execution output
        """
        # This will be implemented by specific Python tools
        # For now, return not implemented
        return CommandResult(
            success=False,
            stdout="",
            stderr=f"Python tool {self.name} execute not implemented",
            exit_code=1,
            command=str(kwargs),
        )

    async def describe(self) -> str:
        """Get Python tool help."""
        from cbx_mcp_k8s.executor.runner import execute_command

        help_cmd = f"{self.name} {self.config.help_flag}"

        result = await execute_command(
            command=help_cmd,
            timeout=10,
            security_config=None,
        )

        if result.success:
            return result.stdout
        else:
            # Fallback to config description
            return f"{self.config.description}\n\nExample: {self.config.example}"

    def get_parameters_schema(self) -> dict[str, Any]:
        """
        Get JSON schema for tool parameters.

        Returns:
            JSON schema dict for MCP tool registration
        """
        if not self.config.parameters:
            return {}

        properties = {}
        required = []

        for param_name, param_config in self.config.parameters.items():
            prop = {
                "type": param_config.get("type", "string"),
                "description": param_config.get("description", ""),
            }
            if "default" in param_config:
                prop["default"] = param_config["default"]

            properties[param_name] = prop

            if param_config.get("required", False):
                required.append(param_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
