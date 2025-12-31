"""
Async command execution engine.

This module handles the actual execution of CLI commands using asyncio
subprocess management. It includes:
- Single command execution
- Piped command execution
- Timeout handling (applied to ALL commands, not just first)
- Output size limiting (checked BEFORE decode for memory safety)
- Proper exit code handling
"""

import asyncio
import shlex
from typing import Any, Optional

from cbx_mcp_k8s.executor.parser import is_pipe_command, parse_command, split_pipe_commands
from cbx_mcp_k8s.executor.types import (
    CommandResult,
    CommandStatus,
)
from cbx_mcp_k8s.executor.validator import CommandValidator


class CommandRunner:
    """
    Executes CLI commands with security validation and resource limits.

    This class is the main entry point for command execution. It:
    1. Validates commands against security policies
    2. Executes commands asynchronously
    3. Handles timeouts and output limits
    4. Returns structured results
    """

    def __init__(
        self,
        validator: CommandValidator,
        default_timeout: int = 60,
        max_output_size: int = 100000,
    ):
        """
        Initialize the command runner.

        Args:
            validator: CommandValidator instance for security checks
            default_timeout: Default timeout in seconds
            max_output_size: Maximum output size in bytes before truncation
        """
        self.validator = validator
        self.default_timeout = default_timeout
        self.max_output_size = max_output_size

    async def execute(
        self,
        command: str,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        """
        Execute a command with validation and resource limits.

        Args:
            command: The command string to execute
            timeout: Optional timeout override in seconds

        Returns:
            CommandResult with execution results

        Raises:
            CommandBlockedError: If command is blocked by security validation
            CommandTimeoutError: If command times out
            CommandExecutionError: If execution fails unexpectedly
        """
        timeout = timeout or self.default_timeout

        # Validate command
        validation = self.validator.validate(command)
        if not validation.allowed:
            return CommandResult(
                status=CommandStatus.BLOCKED,
                stdout="",
                stderr="",
                exit_code=None,
                command=command,
                error_message=validation.reason,
            )

        # Special validation for exec commands
        parsed = parse_command(command)
        if parsed.tool == "kubectl" and parsed.action == "exec":
            exec_validation = self.validator.validate_exec_command(parsed)
            if not exec_validation.allowed:
                return CommandResult(
                    status=CommandStatus.BLOCKED,
                    stdout="",
                    stderr="",
                    exit_code=None,
                    command=command,
                    error_message=exec_validation.reason,
                )

        # Execute command
        try:
            if is_pipe_command(command):
                return await self._execute_piped(command, timeout)
            else:
                return await self._execute_single(command, timeout)
        except asyncio.TimeoutError:
            return CommandResult(
                status=CommandStatus.TIMEOUT,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                exit_code=None,
                command=command,
                error_message=f"Timeout after {timeout}s",
            )
        except Exception as e:
            return CommandResult(
                status=CommandStatus.ERROR,
                stdout="",
                stderr=str(e),
                exit_code=None,
                command=command,
                error_message=f"Execution error: {type(e).__name__}: {e}",
            )

    async def _execute_single(
        self,
        command: str,
        timeout: int,
    ) -> CommandResult:
        """Execute a single (non-piped) command."""
        try:
            args = shlex.split(command)
        except ValueError as e:
            return CommandResult(
                status=CommandStatus.ERROR,
                stdout="",
                stderr=f"Failed to parse command: {e}",
                exit_code=None,
                command=command,
                error_message=f"Parse error: {e}",
            )

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            # Kill the process on timeout
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
            raise

        # Check output size BEFORE decode (memory safety fix from v1)
        truncated = False
        if len(stdout_bytes) > self.max_output_size:
            stdout_bytes = stdout_bytes[: self.max_output_size]
            truncated = True

        # Decode with error handling
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        # Determine status based on exit code
        exit_code = process.returncode
        status = CommandStatus.SUCCESS if exit_code == 0 else CommandStatus.ERROR

        return CommandResult(
            status=status,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,  # Return ACTUAL exit code (v1 fix)
            command=command,
            truncated=truncated,
        )

    async def _execute_piped(
        self,
        command: str,
        timeout: int,
    ) -> CommandResult:
        """
        Execute a piped command chain.

        Each command in the chain gets its own timeout (v1 fix).
        Output from each command is piped to the next.
        """
        commands = split_pipe_commands(command)

        if not commands:
            return CommandResult(
                status=CommandStatus.ERROR,
                stdout="",
                stderr="Empty pipe command",
                exit_code=None,
                command=command,
                error_message="Empty pipe command",
            )

        # Calculate per-command timeout
        # Each command gets equal share of total timeout
        per_command_timeout = max(timeout // len(commands), 10)

        current_input: Optional[bytes] = None
        last_stderr = ""
        last_exit_code: Optional[int] = None

        for i, cmd in enumerate(commands):
            cmd = cmd.strip()
            if not cmd:
                continue

            try:
                args = shlex.split(cmd)
            except ValueError as e:
                return CommandResult(
                    status=CommandStatus.ERROR,
                    stdout="",
                    stderr=f"Failed to parse command {i + 1}: {e}",
                    exit_code=None,
                    command=command,
                    error_message=f"Parse error in pipe segment {i + 1}: {e}",
                )

            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE if current_input else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(input=current_input),
                    timeout=per_command_timeout,  # Timeout for EACH command (v1 fix)
                )
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass
                return CommandResult(
                    status=CommandStatus.TIMEOUT,
                    stdout="",
                    stderr=f"Pipe segment {i + 1} timed out after {per_command_timeout}s: {cmd}",
                    exit_code=None,
                    command=command,
                    error_message=f"Timeout in pipe segment {i + 1}",
                )

            last_exit_code = process.returncode
            last_stderr = stderr_bytes.decode("utf-8", errors="replace")

            # If a command in the pipe fails, we can choose to:
            # Option A: Stop immediately (strict)
            # Option B: Continue and let downstream handle it (like shell)
            # We'll use Option B for now to match shell behavior

            # Pass stdout to next command
            current_input = stdout_bytes

        # Process final output
        truncated = False
        if current_input and len(current_input) > self.max_output_size:
            current_input = current_input[: self.max_output_size]
            truncated = True

        final_stdout = current_input.decode("utf-8", errors="replace") if current_input else ""
        status = CommandStatus.SUCCESS if last_exit_code == 0 else CommandStatus.ERROR

        return CommandResult(
            status=status,
            stdout=final_stdout,
            stderr=last_stderr,
            exit_code=last_exit_code,
            command=command,
            truncated=truncated,
        )


def create_runner(
    security_config: dict[str, Any],
    command_config: Optional[dict[str, Any]] = None,
) -> CommandRunner:
    """
    Factory function to create a CommandRunner.

    Args:
        security_config: Security configuration dictionary
        command_config: Optional command configuration with timeout, max_output_size

    Returns:
        Configured CommandRunner instance
    """
    from cbx_mcp_k8s.executor.validator import create_validator

    validator = create_validator(security_config)

    command_config = command_config or {}
    default_timeout = command_config.get("default_timeout", 60)
    max_output_size = command_config.get("max_output_size", 100000)

    return CommandRunner(
        validator=validator,
        default_timeout=default_timeout,
        max_output_size=max_output_size,
    )


async def execute_command(
    command: str,
    timeout: int = 60,
    security_config: Optional[dict[str, Any]] = None,
    max_output_size: int = 100000,
) -> CommandResult:
    """
    Convenience function to execute a command.

    This is a simpler interface for one-off command execution,
    useful for tool availability checks and simple executions.

    Args:
        command: Command string to execute
        timeout: Timeout in seconds
        security_config: Optional security config. If None, skips validation.
        max_output_size: Max output size in bytes

    Returns:
        CommandResult with execution results
    """
    if security_config:
        from cbx_mcp_k8s.executor.validator import create_validator

        validator = create_validator(security_config)
    else:
        # Create a permissive validator that allows everything
        from cbx_mcp_k8s.executor.validator import CommandValidator

        validator = CommandValidator({"mode": "permissive"})

    runner = CommandRunner(
        validator=validator,
        default_timeout=timeout,
        max_output_size=max_output_size,
    )

    return await runner.execute(command, timeout)
