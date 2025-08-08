# executor/runner.py

import asyncio
import shlex
import time
from asyncio.subprocess import PIPE
from fastmcp import Context
from pydantic.fields import FieldInfo

from ..config import MCP_CONFIG, TOOLS_CONFIG

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
from .validators import is_pipe_command, is_auth_error, get_tool_from_command

from ..utils import get_logger
logger = get_logger(__name__)

async def execute_command(command: str, timeout: int | None = None) -> CommandResult:
    """Execute a Kubernetes CLI command and return the result.

    Validates, executes, and processes the results of a CLI command,
    handling timeouts and output size limits.

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
        first_command = commands[0] # inject_context_namespace(commands[0])

        # We'll execute the commands separately and handle piping ourselves
        command_list = [first_command]
        if len(commands) > 1:
            command_list.extend(commands[1:])
    else:
        # Handle context and namespace for non-piped commands
        command = command   # inject_context_namespace(command)

    # Set timeout
    if timeout is None:
        timeout = command_settings.get('default_timeout')

    logger.debug(f"Executing {'piped ' if is_piped else ''}command: {command}")
    start_time = time.time()

    try:
        if is_piped:
            # Execute piped commands securely by chaining them
            processes = []

            # Split commands for secure execution
            for i, cmd in enumerate(command_list):
                cmd_args = shlex.split(cmd)

                if i == 0:  # First command
                    # First process writes to a pipe
                    first_process = await asyncio.create_subprocess_exec(
                        *cmd_args,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=PIPE,
                    )
                    processes.append(first_process)
                    prev_stdout = first_process.stdout

                else:  # Middle or last commands
                    # Read from previous process's stdout, write to pipe (except last command)
                    next_process = await asyncio.create_subprocess_exec(
                        *cmd_args,
                        stdin=prev_stdout,
                        stdout=PIPE if i < len(command_list) - 1 else PIPE,
                        stderr=PIPE,
                    )
                    processes.append(next_process)
                    if i < len(command_list) - 1:
                        prev_stdout = next_process.stdout

            # We only need to communicate with the last process to get the final output
            last_process = processes[-1]
            process = last_process
        else:
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
        except TimeoutError:
            logger.warning(f"Command timed out after {timeout} seconds: {command}")
            try:
                process.kill()
            except Exception as e:
                logger.error(f"Error killing process: {e}")

            execution_time = time.time() - start_time
            raise CommandTimeoutError(f"Command timed out after {timeout} seconds", {"command": command, "timeout": timeout}) from None

        # Process output
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")
        execution_time = time.time() - start_time

        # Truncate output if necessary
        max_output_size = command_settings.get('max_output_size')
        if len(stdout_str) > max_output_size:
            logger.info(f"Output truncated from {len(stdout_str)} to {max_output_size} characters")
            stdout_str = stdout_str[:max_output_size] + "\n... (output truncated)"

        if process.returncode != 0:
            logger.warning(f"Command failed with return code {process.returncode}: {command}")
            logger.debug(f"Command error output: {stderr_str}")

            error_message = stderr_str or "Command failed with no error output"

            if is_auth_error(stderr_str):
                cli_tool = get_tool_from_command(command)
                auth_error_msg = f"Authentication error: {stderr_str}"

                match cli_tool:
                    case "kubectl":
                        auth_error_msg += "\nPlease check your kubeconfig."
                    case "istioctl":
                        auth_error_msg += "\nPlease check your Istio configuration."
                    case "helm":
                        auth_error_msg += "\nPlease check your Helm repository configuration."
                    case "argocd":
                        auth_error_msg += "\nPlease check your ArgoCD login status."

                raise AuthenticationError(
                    auth_error_msg,
                    {
                        "command": command,
                        "exit_code": process.returncode,
                        "stderr": stderr_str,
                    },
                )
            else:
                raise CommandExecutionError(
                    error_message,
                    {
                        "command": command,
                        "exit_code": process.returncode,
                        "stderr": stderr_str,
                    },
                )

        return CommandResult(status="success", output=stdout_str, exit_code=process.returncode, execution_time=execution_time)
    except asyncio.CancelledError:
        raise
    except (CommandValidationError, CommandExecutionError, AuthenticationError, CommandTimeoutError):
        # Re-raise specific exceptions so they can be caught and handled at the API boundary
        raise
    except Exception as e:
        logger.error(f"Failed to execute command: {str(e)}")
        raise CommandExecutionError(f"Failed to execute command: {str(e)}", {"command": command}) from e

async def execute_tool_command(
        tool: str,
        command: str,
        timeout: int | None,
        ctx: Context | None,
) -> CommandResult:
    """Internal implementation for executing tool commands."""
    logger.info(f"Executing {tool} command: {command}" + (f" with timeout: {timeout}" if timeout else ""))

    command_settings = MCP_CONFIG.get("command")

    # Handle Pydantic Field default for timeout
    actual_timeout = timeout
    if isinstance(timeout, FieldInfo) or timeout is None:
        actual_timeout = command_settings.get('default_timeout')

    # Add tool prefix if not present
    if not command.strip().startswith(tool):
        command = f"{tool} {command}"

    if ctx:
        is_pipe = "|" in command
        message = "Executing" + (" piped" if is_pipe else "") + f" {tool} command"
        await ctx.info(message + (f" with timeout: {actual_timeout}s" if actual_timeout else ""))

    try:
        result = await execute_command(command, timeout=actual_timeout)

        if result["status"] == "success":
            if ctx:
                await ctx.info(f"{tool} command executed successfully")
        else:
            if ctx:
                await ctx.warning(f"{tool} command failed")

        return result
    except CommandValidationError as e:
        logger.warning(f"{tool} command validation error: {e}")
        if ctx:
            await ctx.error(f"Command validation error: {str(e)}")
        return create_error_result(e, command=command)
    except CommandExecutionError as e:
        logger.warning(f"{tool} command execution error: {e}")
        if ctx:
            await ctx.error(f"Command execution error: {str(e)}")
        return create_error_result(e, command=command)
    except AuthenticationError as e:
        logger.warning(f"{tool} command authentication error: {e}")
        if ctx:
            await ctx.error(f"Authentication error: {str(e)}")
        return create_error_result(e, command=command)
    except CommandTimeoutError as e:
        logger.warning(f"{tool} command timeout error: {e}")
        if ctx:
            await ctx.error(f"Command timed out: {str(e)}")
        return create_error_result(e, command=command)
    except Exception as e:
        logger.error(f"Error in execute_{tool}: {e}")
        if ctx:
            await ctx.error(f"Unexpected error: {str(e)}")
        error = CommandExecutionError(f"Unexpected error: {str(e)}", {"command": command})
        return create_error_result(error, command=command)


async def get_command_help(cli_tool: str, help_flag:str, command: str | None = None) -> CommandHelpResult:
    """Get help documentation for a Kubernetes CLI tool or command.

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
    except CommandValidationError as e:
        logger.warning(f"Help command validation error: {e}")
        return CommandHelpResult(
            help_text=f"Command validation error: {str(e)}",
            status="error",
            error={"message": str(e), "code": "VALIDATION_ERROR"},
        )
    except CommandExecutionError as e:
        logger.warning(f"Help command execution error: {e}")
        return CommandHelpResult(
            help_text=f"Command execution error: {str(e)}",
            status="error",
            error={"message": str(e), "code": "EXECUTION_ERROR"},
        )
    except AuthenticationError as e:
        logger.warning(f"Help command authentication error: {e}")
        return CommandHelpResult(
            help_text=f"Authentication error: {str(e)}",
            status="error",
            error={"message": str(e), "code": "AUTH_ERROR"},
        )
    except CommandTimeoutError as e:
        logger.warning(f"Help command timeout error: {e}")
        return CommandHelpResult(
            help_text=f"Command timed out: {str(e)}",
            status="error",
            error={"message": str(e), "code": "TIMEOUT_ERROR"},
        )
    except Exception as e:
        logger.error(f"Unexpected error while getting command help: {e}", exc_info=True)
        return CommandHelpResult(
            help_text=f"Error retrieving help: {str(e)}",
            status="error",
            error={"message": f"Error retrieving help: {str(e)}", "code": "INTERNAL_ERROR"},
        )






