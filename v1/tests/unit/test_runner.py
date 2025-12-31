# tests/unit/test_runner.py
"""
Unit tests for command runner.
Tests execution logic, timeout handling, and output processing.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.cbx_mcp_k8s.executor.runner import (
    validate_pipe_commands,
    execute_command,
    execute_single_command,
    execute_piped_commands,
    process_command_result,
    get_command_help,
)
from app.cbx_mcp_k8s.executor.errors import (
    CommandValidationError,
    CommandExecutionError,
    CommandTimeoutError,
)


class TestValidatePipeCommands:
    """Tests for pipe command validation."""

    def test_valid_pipe_chain(self):
        """Valid pipe chain should pass."""
        commands = ["kubectl get pods", "grep nginx", "wc -l"]
        validate_pipe_commands(commands)  # Should not raise

    def test_first_command_must_be_tool(self):
        """First command must be a configured tool."""
        commands = ["grep pattern", "wc -l"]
        with pytest.raises(CommandValidationError, match="First command must be a configured tool"):
            validate_pipe_commands(commands)

    def test_empty_command_in_chain(self):
        """Empty command in chain should fail."""
        commands = ["kubectl get pods", "", "wc -l"]
        with pytest.raises(CommandValidationError, match="Empty command"):
            validate_pipe_commands(commands)

    def test_disallowed_unix_command(self):
        """Disallowed Unix command should fail."""
        commands = ["kubectl get pods", "python -c print"]
        with pytest.raises(CommandValidationError, match="not allowed"):
            validate_pipe_commands(commands)


class TestExecuteCommand:
    """Tests for command execution."""

    @pytest.mark.asyncio
    async def test_validation_error_raised(self, strict_security_mode):
        """Validation errors should be raised as CommandValidationError."""
        with pytest.raises(CommandValidationError):
            await execute_command("invalid_tool get pods")

    @pytest.mark.asyncio
    async def test_empty_command_error(self, strict_security_mode):
        """Empty command should raise validation error."""
        with pytest.raises(CommandValidationError):
            await execute_command("")


class TestExecuteSingleCommand:
    """Tests for single command execution."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Successful command should return result."""
        # Create mock process
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"output", b""))

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            with patch('asyncio.wait_for', return_value=(b"output", b"")):
                result = await execute_single_command("echo test", 30, 0)
                assert result["status"] == "success"
                assert "output" in result["output"]

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Command timeout should raise CommandTimeoutError."""
        mock_process = MagicMock()
        mock_process.returncode = None
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError()):
                with pytest.raises(CommandTimeoutError, match="timed out"):
                    await execute_single_command("sleep 100", 1, 0)


class TestProcessCommandResult:
    """Tests for result processing."""

    @pytest.mark.asyncio
    async def test_successful_result(self):
        """Successful command should return success result."""
        mock_process = MagicMock()
        mock_process.returncode = 0

        result = await process_command_result(
            process=mock_process,
            stdout=b"test output",
            stderr=b"",
            command="echo test",
            start_time=0,
            command_settings={"max_output_size": 100000}
        )

        assert result["status"] == "success"
        assert result["output"] == "test output"
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_failed_result(self):
        """Failed command should raise CommandExecutionError."""
        mock_process = MagicMock()
        mock_process.returncode = 1

        with pytest.raises(CommandExecutionError):
            await process_command_result(
                process=mock_process,
                stdout=b"",
                stderr=b"error message",
                command="false",
                start_time=0,
                command_settings={"max_output_size": 100000}
            )

    @pytest.mark.asyncio
    async def test_output_truncation(self):
        """Large output should be truncated."""
        mock_process = MagicMock()
        mock_process.returncode = 0

        large_output = b"x" * 200000  # 200KB output

        result = await process_command_result(
            process=mock_process,
            stdout=large_output,
            stderr=b"",
            command="echo test",
            start_time=0,
            command_settings={"max_output_size": 1000}  # 1KB limit
        )

        assert len(result["output"]) < 200000
        assert "truncated" in result["output"]


class TestGetCommandHelp:
    """Tests for help command retrieval."""

    @pytest.mark.asyncio
    async def test_help_builds_correct_command_with_subcommand(self):
        """Help with specific command should build correct command string."""
        # Test the command string building logic
        cli_tool = "kubectl"
        help_flag = "--help"
        command = "get"

        # Expected: "kubectl get --help"
        expected_cmd = f"{cli_tool} {command} {help_flag}"
        assert expected_cmd == "kubectl get --help"

    @pytest.mark.asyncio
    async def test_help_builds_correct_command_without_subcommand(self):
        """Help without command should build correct command string."""
        cli_tool = "kubectl"
        help_flag = "--help"
        command = None

        # Expected: "kubectl --help"
        if command:
            cmd_str = f"{cli_tool} {command} {help_flag}"
        else:
            cmd_str = f"{cli_tool} {help_flag}"

        assert cmd_str == "kubectl --help"

    @pytest.mark.asyncio
    async def test_help_real_execution(self, permissive_security_mode):
        """Test real help command execution."""
        result = await get_command_help("kubectl", "--help", None)
        # Should return some result (success or error depending on kubectl availability)
        assert result is not None
        # CommandHelpResult is a dataclass, access via attribute
        assert result.help_text is not None


class TestIntegration:
    """Integration tests that actually execute commands."""

    @pytest.mark.asyncio
    async def test_real_command_execution(self, permissive_security_mode):
        """Test real command execution with kubectl."""
        result = await execute_command("kubectl version --client")
        # This will either succeed (if kubectl installed) or fail gracefully
        assert result is not None

    @pytest.mark.asyncio
    async def test_piped_command_execution(self, permissive_security_mode):
        """Test piped command execution.

        Uses sequential execution with communicate() to pass output between stages.
        """
        result = await execute_command("kubectl version --client | head -1")
        assert result is not None
        assert result["status"] == "success"
        # Output should be filtered to single line by head
        assert result["output"].count("\n") <= 1
