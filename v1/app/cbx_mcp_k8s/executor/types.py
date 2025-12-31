# executor/types.py

from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict
import shlex

class ErrorDetailsNested(TypedDict, total=False):
    """Type definition for nested error details."""

    command: str
    exit_code: int
    stderr: str


class ErrorDetails(TypedDict, total=False):
    """Type definition for detailed error information matching the spec."""

    message: str
    code: str
    details: ErrorDetailsNested  # Use the nested type here


class CommandResult(TypedDict):
    """Type definition for command execution results following the specification."""

    status: Literal["success", "error"]
    output: str
    exit_code: NotRequired[int]
    execution_time: NotRequired[float]
    error: NotRequired[ErrorDetails]


@dataclass
class CommandHelpResult:
    """Type definition for command help results."""

    help_text: str
    status: str = "success"
    error: ErrorDetails | None = None
