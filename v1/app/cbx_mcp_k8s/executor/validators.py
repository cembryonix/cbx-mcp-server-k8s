# executor/validators.py

import shlex
import re

from ..utils import get_logger
from ..config import MCP_CONFIG, SECURITY_CONFIG, TOOLS_CONFIG

logger = get_logger(__name__)

def is_auth_error(error_output: str) -> bool:
    """Detect if an error is related to authentication.

    Args:
        error_output: The error output from CLI tool

    Returns:
        True if the error is related to authentication, False otherwise
    """
    auth_error_patterns = [
        "Unable to connect to the server",
        "Unauthorized",
        "forbidden",
        "Invalid kubeconfig",
        "Unable to load authentication",
        "Error loading config",
        "no configuration has been provided",
        "You must be logged in",  # For argocd
        "Error: Helm repo",  # For Helm repo authentication
    ]
    return any(pattern.lower() in error_output.lower() for pattern in auth_error_patterns)


def get_tool_from_command(command: str) -> str | None:
    """Extract the CLI tool from a command string.

    Args:
        command: The command string

    Returns:
        The CLI tool name or None if not found
    """
    cmd_parts = shlex.split(command)
    if not cmd_parts:
        return None

    return cmd_parts[0] if cmd_parts[0] in TOOLS_CONFIG else None





def validate_unix_command(command: str) -> bool:
    """Validate that a command is an allowed Unix command.

    Args:
        command: The Unix command to validate

    Returns:
        True if the command is valid, False otherwise
    """
    cmd_parts = shlex.split(command)
    if not cmd_parts:
        return False

    # Check if the command is in the allowed list
    return cmd_parts[0] in SECURITY_CONFIG.get('allowed_unix_commands',[])         # ALLOWED_UNIX_COMMANDS


def is_pipe_command(command: str) -> bool:
    """Check if a command contains a pipe operator.

    Args:
        command: The command to check

    Returns:
        True if the command contains a pipe operator, False otherwise
    """
    # Simple check for pipe operator that's not inside quotes
    in_single_quote = False
    in_double_quote = False

    for i, char in enumerate(command):
        if char == "'" and (i == 0 or command[i - 1] != "\\"):
            in_single_quote = not in_single_quote
        elif char == '"' and (i == 0 or command[i - 1] != "\\"):
            in_double_quote = not in_double_quote
        elif char == "|" and not in_single_quote and not in_double_quote:
            return True

    return False

def is_safe_exec_command(command: str) -> bool:
    """Check if a kubectl exec command is safe to execute.

    We consider a kubectl exec command safe if:
    1. It's explicitly interactive (-it, -ti flags) and the user is aware of this
    2. It executes a specific command rather than opening a general shell
    3. It uses shells (bash/sh) only with specific commands (-c flag)

    Args:
        command: The kubectl exec command

    Returns:
        True if the command is safe, False otherwise
    """
    if not command.startswith("kubectl exec"):
        return True  # Not an exec command

    # Special cases: help and version are always safe
    if " --help" in command or " -h" in command or " version" in command:
        return True

    # Check for explicit interactive mode
    has_interactive = any(flag in command for flag in [" -i ", " --stdin ", " -it ", " -ti ", " -t ", " --tty "])

    # List of dangerous shell commands that should not be executed without arguments
    dangerous_shell_patterns = [
        " -- sh",
        " -- bash",
        " -- /bin/sh",
        " -- /bin/bash",
        " -- zsh",
        " -- /bin/zsh",
        " -- ksh",
        " -- /bin/ksh",
        " -- csh",
        " -- /bin/csh",
        " -- /usr/bin/bash",
        " -- /usr/bin/sh",
        " -- /usr/bin/zsh",
        " -- /usr/bin/ksh",
        " -- /usr/bin/csh",
    ]

    # Check if any of the dangerous shell patterns are present
    has_shell_pattern = False
    for pattern in dangerous_shell_patterns:
        if pattern in command + " ":  # Add space to match end of command
            has_shell_pattern = True
            # If shell is used with -c flag to run a specific command, that's acceptable
            if f"{pattern} -c " in command or f"{pattern.strip()} -c " in command:
                return True

    # Safe conditions:
    # 1. Not using a shell at all
    # 2. Interactive mode is explicitly requested (user knows they're getting a shell)
    if not has_shell_pattern:
        return True  # Not using a shell

    if has_interactive and has_shell_pattern:
        # If interactive is explicitly requested and using a shell,
        # we consider it an intentional interactive shell request
        return True

    # Default: If using a shell without explicit command (-c) and not explicitly
    # requesting interactive mode, consider it unsafe
    return False


def validate_k8s_command(command: str) -> None:
    """Validate that the command is a proper Kubernetes CLI tool command.

    Args:
        command: The Kubernetes CLI command to validate

    Raises:
        ValueError: If the command is invalid
    """
    logger.debug(f"Validating K8s command: {command}")

    security_mode = MCP_CONFIG.get('security').get('security_mode')

    # Skip validation in permissive mode
    if security_mode == "permissive":
        logger.warning(f"Running in permissive security mode, skipping validation for: {command}")
        return

    cmd_parts = shlex.split(command)
    if not cmd_parts:
        raise ValueError("Empty command")

    cli_tool = cmd_parts[0]
    if not is_valid_k8s_tool(cli_tool):
        allowed_tool_names = list(TOOLS_CONFIG.keys())
        raise ValueError(f"Command must start with a supported CLI tool: {', '.join(allowed_tool_names)}")

    if len(cmd_parts) < 2:
        raise ValueError(f"Command must include a {cli_tool} action")

    # Special case for kubectl exec
    if cli_tool == "kubectl" and "exec" in cmd_parts:
        if not is_safe_exec_command(command):
            raise ValueError("Interactive shells via kubectl exec are restricted. Use explicit commands or proper flags (-it, --command, etc).")

    # Apply regex rules for more advanced pattern matching
    # Apply regex rules for more advanced pattern matching
    regex_rules = SECURITY_CONFIG.get('regex_rules', {})
    if regex_rules and cli_tool in regex_rules and regex_rules[cli_tool]:
        for rule in regex_rules[cli_tool]:
            # Since you control the rule structure in YAML, these keys should exist
            pattern = re.compile(rule['pattern'])
            if pattern.search(command):
                raise ValueError(
                    rule.get('error_message', f"Command matches restricted pattern: {rule['pattern']}")
                )

    # Check against dangerous commands
    dangerous_commands = SECURITY_CONFIG['dangerous_commands']
    safe_patterns = SECURITY_CONFIG['safe_patterns']

    if cli_tool in dangerous_commands and dangerous_commands[cli_tool]:
        for dangerous_cmd in dangerous_commands[cli_tool]:
            if command.startswith(dangerous_cmd):
                # Check if it matches a safe pattern
                if cli_tool in safe_patterns and safe_patterns[cli_tool]:
                    if any(command.startswith(safe_pattern) for safe_pattern in safe_patterns[cli_tool]):
                        logger.debug(f"Command matches safe pattern: {command}")
                        return  # Safe pattern match, allow command

                raise ValueError(
                    f"This command ({dangerous_cmd}) is restricted for safety reasons. Please use a more specific form with resource type and name."
                )

    logger.debug(f"Command validation successful: {command}")


def validate_pipe_command(pipe_command: str) -> None:
    """Validate a command that contains pipes.

    This checks both Kubernetes CLI commands and Unix commands within a pipe chain.

    Args:
        pipe_command: The piped command to validate

    Raises:
        ValueError: If any command in the pipe is invalid
    """
    logger.debug(f"Validating pipe command: {pipe_command}")

    commands = split_pipe_command(pipe_command)

    if not commands:
        raise ValueError("Empty command")

    # First command must be a Kubernetes CLI command
    validate_k8s_command(commands[0])

    # Subsequent commands should be valid Unix commands
    for i, cmd in enumerate(commands[1:], 1):
        cmd_parts = shlex.split(cmd)
        if not cmd_parts:
            raise ValueError(f"Empty command at position {i} in pipe")

        if not validate_unix_command(cmd):
            raise ValueError(
                f"Command '{cmd_parts[0]}' at position {i} in pipe is not allowed. "
                f"Only kubectl, istioctl, helm, argocd commands and basic Unix utilities are permitted."
            )

    logger.debug(f"Pipe command validation successful: {pipe_command}")


def validate_command(command: str) -> None:
    """Centralized validation for all commands."""

    logger.debug(f"Validating command: {command}")

    # Keys must always exist either from package defaults or from user
    security_mode = MCP_CONFIG['security']['security_mode']

    # Skip validation in permissive mode
    if security_mode == "permissive":
        logger.warning(f"Running in permissive security mode, skipping validation for: {command}")
        return

    if is_pipe_command(command):
        validate_pipe_command(command)
    else:
        validate_k8s_command(command)

    logger.debug(f"Command validation successful: {command}")


def is_valid_k8s_tool(command: str) -> bool:
    """Check if a command starts with a valid Kubernetes CLI tool.

    Args:
        command: The command to check

    Returns:
        True if the command starts with a valid Kubernetes CLI tool, False otherwise
    """
    cmd_parts = shlex.split(command)
    if not cmd_parts:
        return False

    return cmd_parts[0] in TOOLS_CONFIG

def split_pipe_command(pipe_command: str) -> list[str]:
    """Split a piped command into individual commands.

    Args:
        pipe_command: The piped command string

    Returns:
        List of individual command strings
    """
    if not pipe_command:
        return [""]  # Return a list with an empty string for empty input

    commands = []
    current_command = ""
    in_single_quote = False
    in_double_quote = False

    for i, char in enumerate(pipe_command):
        if char == "'" and (i == 0 or pipe_command[i - 1] != "\\"):
            in_single_quote = not in_single_quote
            current_command += char
        elif char == '"' and (i == 0 or pipe_command[i - 1] != "\\"):
            in_double_quote = not in_double_quote
            current_command += char
        elif char == "|" and not in_single_quote and not in_double_quote:
            commands.append(current_command.strip())
            current_command = ""
        else:
            current_command += char

    if current_command.strip():
        commands.append(current_command.strip())

    return commands
