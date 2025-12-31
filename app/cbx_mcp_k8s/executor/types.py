"""
Type definitions for command execution.

This module defines the data structures used throughout the executor.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CommandStatus(str, Enum):
    """Status of command execution."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"  # Blocked by security validation


@dataclass
class CommandResult:
    """
    Result of a command execution.

    Attributes:
        status: Execution status
        stdout: Standard output (may be truncated)
        stderr: Standard error output
        exit_code: Process exit code (None if not available, e.g., timeout)
        command: The command that was executed
        truncated: Whether output was truncated due to size limits
        error_message: Human-readable error message (for blocked/error status)
    """

    status: CommandStatus
    stdout: str
    stderr: str
    exit_code: Optional[int]
    command: str
    truncated: bool = False
    error_message: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if command executed successfully."""
        return self.status == CommandStatus.SUCCESS and self.exit_code == 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "command": self.command,
            "truncated": self.truncated,
            "error_message": self.error_message,
        }


@dataclass
class ParsedCommand:
    """
    Structured representation of a CLI command.

    This provides a parsed view of commands for security validation,
    replacing simple string prefix matching.

    Attributes:
        tool: The CLI tool (kubectl, helm, argocd, aws)
        action: The primary action/verb (get, delete, apply, etc.)
        resource: Resource type if applicable (pod, deployment, etc.)
        name: Resource name if specified
        args: Positional arguments
        flags: Parsed flags as key-value pairs
        raw: Original raw command string
    """

    tool: str
    action: str
    resource: Optional[str] = None
    name: Optional[str] = None
    args: list[str] = field(default_factory=list)
    flags: dict[str, Optional[str]] = field(default_factory=dict)
    raw: str = ""

    def has_flag(self, *flag_names: str) -> bool:
        """Check if any of the given flags are present."""
        return any(f in self.flags for f in flag_names)

    def get_flag(self, *flag_names: str, default: Optional[str] = None) -> Optional[str]:
        """Get the value of the first matching flag."""
        for f in flag_names:
            if f in self.flags:
                return self.flags[f]
        return default

    def get_namespace(self) -> Optional[str]:
        """Get the namespace from flags."""
        return self.get_flag("-n", "--namespace")


@dataclass
class ValidationResult:
    """
    Result of security validation.

    Attributes:
        allowed: Whether the command is allowed
        reason: Explanation of why command was blocked (if not allowed)
        rule: The specific rule that blocked the command
    """

    allowed: bool
    reason: Optional[str] = None
    rule: Optional[str] = None

    @classmethod
    def allow(cls) -> "ValidationResult":
        """Create an allowing result."""
        return cls(allowed=True)

    @classmethod
    def block(cls, reason: str, rule: Optional[str] = None) -> "ValidationResult":
        """Create a blocking result."""
        return cls(allowed=False, reason=reason, rule=rule)


class ExecutorError(Exception):
    """Base exception for executor errors."""

    pass


class CommandBlockedError(ExecutorError):
    """Raised when a command is blocked by security validation."""

    def __init__(self, message: str, rule: Optional[str] = None):
        super().__init__(message)
        self.rule = rule


class CommandTimeoutError(ExecutorError):
    """Raised when a command times out."""

    def __init__(self, command: str, timeout: int):
        super().__init__(f"Command timed out after {timeout}s: {command}")
        self.command = command
        self.timeout = timeout


class CommandExecutionError(ExecutorError):
    """Raised when command execution fails unexpectedly."""

    pass
