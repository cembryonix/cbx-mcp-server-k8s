# executor/runner.py

import asyncio
import shlex
import time
from asyncio.subprocess import PIPE
from fastmcp import Context
from pydantic.fields import FieldInfo

from ..config import MCP_CONFIG, TOOLS_CONFIG, SECURITY_CONFIG

from .errors import (
    AuthenticationError,
    CommandExecutionError,
    CommandTimeoutError,
    CommandValidationError,
    create_error_result
)
from .validators import validate_command, split_pipe_command
from .types import (
    CommandHelpResult,
    CommandResult,
)
from .validators import is_pipe_command, get_tool_from_command

from ..utils import get_logger

logger = get_logger(__name__)


def validate_pipe_commands(command_list: list[str]) -> None:
    """Validate all commands in pipe chain.

    Args:
        command_list: List of commands in the pipe chain

    Raises:
        CommandValidationError: If any command in the chain is invalid
    """
    for i, cmd in enumerate(command_list):
        cmd_parts = shlex.split(cmd.strip())
        if not cmd_parts:
            raise CommandValidationError(f"Empty command at stage {i + 1}")

        tool_name = cmd_parts[0]

        if i == 0:
            # First command must be a configured tool
            if tool_name not in TOOLS_CONFIG:
                raise CommandValidationError(
                    f"First command must be a configured tool. Got '{tool_name}', "
                    f"available tools: {list(TOOLS_CONFIG.keys())}"
                )
        else:
            # Subsequent commands must be allowed unix commands
            if tool_name not in SECURITY_CONFIG.get("allowed_unix_commands"):
                raise CommandValidationError(
                    f"Pipe command '{tool_name}' not allowed at stage {i + 1}. "
                    f"Allowed commands: {SECURITY_CONFIG.get("allowed_unix_commands")}"
                )


async def execute_command(command: str, timeout: int | None = None) -> CommandResult:
    """Execute a CLI command and return the result.

    Validates, executes, and processes the results of a CLI command,
    handling timeouts and output size limits. For piped commands,
    applies timeout only to the first command.

    Args:
        command: The CLI command to execute (must start with supported CLI tool)
        timeout: Optional timeout in seconds (defaults to DEFAULT_TIMEOUT)

    Returns:
        CommandResult containing output and status

    Raises:
        CommandValidationError: If the command is invalid
        CommandExecutionError: If the command fails to execute
        AuthenticationError: If authentication fails
        CommandTimeoutError: If the command times out
    """

    command_settings = MCP_CONFIG.get("command")

    # Validate the command
    try:
        validate_command(command)
    except ValueError as e:
        raise CommandValidationError(str(e), {"command": command}) from e

    # Handle piped commands
    is_piped = is_pipe_command(command)
    if is_piped:
        commands = split_pipe_command(command)
        first_command = commands[0]  # inject_context_namespace(commands[0])

        # We'll execute the commands separately and handle piping ourselves
        command_list = [first_command]
        if len(commands) > 1:
            command_list.extend(commands[1:])

        # Validate all commands in pipe chain before execution (fail fast)
        try:
            validate_pipe_commands(command_list)
        except CommandValidationError:
            raise  # Re-raise with original context
    else:
        # Handle context and namespace for non-piped commands
        command = command  # inject_context_namespace(command)

    # Set timeout
    if timeout is None:
        timeout = command_settings.get('default_timeout')

    logger.debug(f"Executing {'piped ' if is_piped else ''}command: {command}")
    start_time = time.time()

    try:
        if is_piped:
            return await execute_piped_commands(command_list, timeout, start_time)
        else:
            return await execute_single_command(command, timeout, start_time)

    except asyncio.CancelledError:
        raise
    except (CommandValidationError, CommandExecutionError, AuthenticationError, CommandTimeoutError):
        # Re-raise specific exceptions so they can be caught and handled at the API boundary
        raise
    except Exception as e:
        logger.error(f"Failed to execute command: {str(e)}")
        raise CommandExecutionError(f"Failed to execute command: {str(e)}", {"command": command}) from e


async def execute_single_command(command: str, timeout: int, start_time: float) -> CommandResult:
    """Execute a single non-piped command."""
    command_settings = MCP_CONFIG.get("command")

    # Use safer create_subprocess_exec for non-piped commands
    cmd_args = shlex.split(command)
    process = await asyncio.create_subprocess_exec(
        *cmd_args,
        stdout=PIPE,
        stderr=PIPE,
    )

    # Wait for the process to complete with timeout
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        logger.debug(f"Command completed with return code: {process.returncode}")
    except asyncio.TimeoutError:
        logger.warning(f"Command timed out after {timeout} seconds: {command}")
        try:
            process.kill()
            await process.wait()  # Ensure process is cleaned up
        except Exception as e:
            logger.error(f"Error killing process: {e}")

        execution_time = time.time() - start_time
        raise CommandTimeoutError(
            f"Command timed out after {timeout} seconds",
            {"command": command, "timeout": timeout}
        ) from None

    return await process_command_result(
        process, stdout, stderr, command, start_time, command_settings
    )


async def execute_piped_commands(command_list: list[str], timeout: int, start_time: float) -> CommandResult:
    """Execute piped commands sequentially, passing output between stages.

    Uses communicate() to capture output from each stage and pass it as input
    to the next stage. Timeout is applied only to the first command.

    Args:
        command_list: List of commands to execute in sequence
        timeout: Timeout in seconds (applied only to first command)
        start_time: Start time for execution timing

    Returns:
        CommandResult from the final command in the pipe chain
    """
    command_settings = MCP_CONFIG.get("command")
    original_command = " | ".join(command_list)
    current_input: bytes | None = None
    current_process: asyncio.subprocess.Process | None = None

    for i, cmd in enumerate(command_list):
        cmd_args = shlex.split(cmd)
        stage_num = i + 1
        is_first = (i == 0)
        is_last = (i == len(command_list) - 1)

        logger.debug(f"Executing pipe stage {stage_num}/{len(command_list)}: {cmd}")

        try:
            current_process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdin=PIPE if current_input is not None else None,
                stdout=PIPE,
                stderr=PIPE,
            )

            if is_first:
                # Apply timeout only to first command
                try:
                    stdout, stderr = await asyncio.wait_for(
                        current_process.communicate(input=current_input),
                        timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"First command in pipe timed out after {timeout} seconds: {cmd}")
                    try:
                        current_process.kill()
                        await current_process.wait()
                    except Exception as e:
                        logger.error(f"Error killing timed out process: {e}")

                    raise CommandTimeoutError(
                        f"First command in pipe timed out after {timeout} seconds",
                        {
                            "command": original_command,
                            "timeout": timeout,
                            "timed_out_command": cmd
                        }
                    ) from None
            else:
                # Subsequent commands run without timeout
                stdout, stderr = await current_process.communicate(input=current_input)

            # Check for command failure
            if current_process.returncode != 0:
                stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""
                logger.warning(f"Pipe stage {stage_num} failed with return code {current_process.returncode}: {cmd}")

                raise CommandExecutionError(
                    f"Command failed at stage {stage_num}: {cmd}",
                    {
                        "command": original_command,
                        "failed_stage": stage_num,
                        "failed_command": cmd,
                        "exit_code": current_process.returncode,
                        "stderr": stderr_str,
                    },
                )

            logger.debug(f"Pipe stage {stage_num} completed successfully")

            # Pass stdout as input to next stage (unless this is the last command)
            if not is_last:
                current_input = stdout

        except (CommandTimeoutError, CommandExecutionError):
            raise
        except Exception as e:
            logger.error(f"Unexpected error at pipe stage {stage_num}: {e}")
            if current_process and current_process.returncode is None:
                try:
                    current_process.kill()
                    await current_process.wait()
                except Exception as kill_error:
                    logger.error(f"Error killing process: {kill_error}")
            raise CommandExecutionError(
                f"Unexpected error at stage {stage_num}: {str(e)}",
                {
                    "command": original_command,
                    "failed_stage": stage_num,
                    "failed_command": cmd,
                },
            ) from e

    # Process final result
    return await process_command_result(
        current_process, stdout, stderr, original_command, start_time, command_settings
    )


async def kill_process_chain(processes: list[asyncio.subprocess.Process]) -> None:
    """Kill a list of processes and wait for them to terminate."""
    for process in processes:
        if process.returncode is None:  # Process is still running
            try:
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except Exception as e:
                logger.error(f"Error killing process {process.pid}: {e}")


async def process_command_result(
        process: asyncio.subprocess.Process,
        stdout: bytes,
        stderr: bytes,
        command: str,
        start_time: float,
        command_settings: dict
) -> CommandResult:
    """Process command execution results and return CommandResult."""

    # Process output
    stdout_str = stdout.decode("utf-8", errors="replace")
    stderr_str = stderr.decode("utf-8", errors="replace")
    execution_time = time.time() - start_time

    # Ensure we always have a valid exit code
    exit_code = process.returncode if process.returncode is not None else -1

    # Truncate output if necessary
    max_output_size = command_settings.get('max_output_size')
    if len(stdout_str) > max_output_size:
        logger.info(f"Output truncated from {len(stdout_str)} to {max_output_size} characters")
        stdout_str = stdout_str[:max_output_size] + "\n... (output truncated)"

    if exit_code != 0:
        logger.warning(f"Command failed with return code {exit_code}: {command}")
        logger.debug(f"Command error output: {stderr_str}")

        error_message = stderr_str or "Command failed with no error output"

        raise CommandExecutionError(
            error_message,
            {
                "command": command,
                "exit_code": exit_code,
                "stderr": stderr_str,
            },
        )

    return CommandResult(
        status="success",
        output=stdout_str,
        exit_code=exit_code,
        execution_time=execution_time
    )


async def send_ctx_error(ctx: Context, error_type: str, error: Exception, tool: str) -> None:
    """Send context-specific error messages."""
    if not ctx:
        return

    error_details = getattr(error, 'details', {})

    if error_type == "execution" and 'failed_stage' in error_details:
        await ctx.error(f"Command failed at stage {error_details['failed_stage']}: {str(error)}")
    elif error_type == "timeout" and 'timed_out_command' in error_details:
        await ctx.error(f"First command timed out: {error_details['timed_out_command']}")
    else:
        error_messages = {
            "validation": f"Command validation error: {str(error)}",
            "execution": f"Command execution error: {str(error)}",
            "auth": f"Authentication error: {str(error)}",
            "timeout": f"Command timed out: {str(error)}",
            "unexpected": f"Unexpected error: {str(error)}"
        }
        await ctx.error(error_messages.get(error_type, f"Error: {str(error)}"))


async def execute_tool_command(
        tool: str,
        command: str,
        timeout: int | None,
        ctx: Context | None,
) -> CommandResult:
    """Internal implementation for executing tool commands."""
    logger.info(f"Executing {tool} command: {command}" + (f" with timeout: {timeout}" if timeout else ""))

    # Resolve timeout
    actual_timeout = timeout
    if isinstance(timeout, FieldInfo) or timeout is None:
        actual_timeout = MCP_CONFIG.get("command").get('default_timeout')

    # Add tool prefix if not present
    if not command.strip().startswith(tool):
        command = f"{tool} {command}"

    # Send initial context message
    if ctx:
        pipe_text = " piped" if "|" in command else ""
        timeout_text = f" with timeout: {actual_timeout}s" if actual_timeout else ""
        await ctx.info(f"Executing{pipe_text} {tool} command{timeout_text}")

    # Execute command with error handling
    error_handlers = {
        CommandValidationError: ("validation", "validation error"),
        CommandExecutionError: ("execution", "execution error"),
        AuthenticationError: ("auth", "authentication error"),
        CommandTimeoutError: ("timeout", "timeout error")
    }

    try:
        result = await execute_command(command, timeout=actual_timeout)

        if ctx:
            status_msg = f"{tool} command executed successfully" if result[
                                                                        "status"] == "success" else f"{tool} command failed"
            if result["status"] == "success":
                await ctx.info(status_msg)
            else:
                await ctx.warning(status_msg)

        return result

    except Exception as e:
        # Handle specific exceptions
        for exception_type, (error_type, log_suffix) in error_handlers.items():
            if isinstance(e, exception_type):
                logger.warning(f"{tool} command {log_suffix}: {e}")
                await send_ctx_error(ctx, error_type, e, tool)
                return create_error_result(e, command=command, exit_code=0)

        # Handle unexpected exceptions
        logger.error(f"Error in execute_{tool}: {e}")
        await send_ctx_error(ctx, "unexpected", e, tool)
        error = CommandExecutionError(f"Unexpected error: {str(e)}", {"command": command})
        return create_error_result(error, command=command, exit_code=0)


async def get_command_help(cli_tool: str, help_flag: str, command: str | None = None) -> CommandHelpResult:
    """Get help documentation for a two-level CLI tool or command.

    Retrieves the help documentation for a specified CLI tool or command
    by executing the appropriate help command.

    Args:
        cli_tool: The CLI tool name (kubectl, istioctl, helm, argocd)
        help_flag: flag in the help retrieval string "{tool} {command} {help_flag}"
        command: Optional command within the CLI tool (e.g. "get" in  "kubectl get" )

    Returns:
        CommandHelpResult containing the help text
    """

    if command:
        cmd_str = f"{cli_tool} {command} {help_flag}"
    else:
        cmd_str = f"{cli_tool} {help_flag}"

    try:
        logger.debug(f"Getting command help for: {cmd_str}")
        result = await execute_command(cmd_str)
        return CommandHelpResult(help_text=result["output"])
    except CommandExecutionError as e:
        # Most likely cause: tool not installed or not in PATH
        logger.warning(f"Help command execution error: {e}")
        return CommandHelpResult(
            help_text=f"Unable to get help: {str(e)}",
            status="error",
            error={"message": str(e), "code": "EXECUTION_ERROR"},
        )
    except Exception as e:
        # Catch-all for unexpected system issues
        logger.error(f"Unexpected error while getting command help: {e}", exc_info=True)
        return CommandHelpResult(
            help_text=f"Error retrieving help: {str(e)}",
            status="error",
            error={"message": f"Error retrieving help: {str(e)}", "code": "INTERNAL_ERROR"},
        )