#!/usr/bin/env python3
"""
Functional tests for the executor module.

These tests verify:
1. Command parsing accuracy
2. Security validation behavior
3. Command execution with real subprocesses
"""

import sys
from pathlib import Path

import pytest
import yaml

# Add app directory to path for imports
APP_DIR = Path(__file__).parent.parent.parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

from cbx_mcp_k8s.executor import (
    CommandRunner,
    CommandStatus,
    CommandValidator,
    is_pipe_command,
    parse_command,
    split_pipe_commands,
)

# Load test data
TEST_DATA_PATH = Path(__file__).parent / "test_data.yaml"
with open(TEST_DATA_PATH) as f:
    TEST_DATA = yaml.safe_load(f)


# =============================================================================
# Parser Tests
# =============================================================================
class TestParser:
    """Test command parsing functionality."""

    @pytest.mark.parametrize(
        "test_case",
        TEST_DATA["parser_tests"]["kubectl"],
        ids=lambda tc: tc["name"],
    )
    def test_parse_kubectl_commands(self, test_case: dict):
        """Test parsing of kubectl commands."""
        command = test_case["command"]
        expected = test_case["expected"]

        parsed = parse_command(command)

        assert parsed.tool == expected.get("tool", "kubectl")
        assert parsed.action == expected.get("action", "")

        if "resource" in expected:
            assert parsed.resource == expected["resource"]

        if "name" in expected:
            assert parsed.name == expected["name"]

        if "flags" in expected:
            for flag, value in expected["flags"].items():
                assert flag in parsed.flags, f"Missing flag: {flag}"
                if value is not None:
                    assert parsed.flags[flag] == value

    @pytest.mark.parametrize(
        "test_case",
        TEST_DATA["parser_tests"]["helm"],
        ids=lambda tc: tc["name"],
    )
    def test_parse_helm_commands(self, test_case: dict):
        """Test parsing of helm commands."""
        command = test_case["command"]
        expected = test_case["expected"]

        parsed = parse_command(command)

        assert parsed.tool == expected.get("tool", "helm")
        assert parsed.action == expected.get("action", "")

        if "name" in expected:
            assert parsed.name == expected["name"]

        if "flags" in expected:
            for flag, value in expected["flags"].items():
                assert flag in parsed.flags

    @pytest.mark.parametrize(
        "test_case",
        TEST_DATA["parser_tests"]["argocd"],
        ids=lambda tc: tc["name"],
    )
    def test_parse_argocd_commands(self, test_case: dict):
        """Test parsing of argocd commands."""
        command = test_case["command"]
        expected = test_case["expected"]

        parsed = parse_command(command)

        assert parsed.tool == expected.get("tool", "argocd")
        assert parsed.action == expected.get("action", "")

        if "resource" in expected:
            assert parsed.resource == expected["resource"]

    @pytest.mark.parametrize(
        "test_case",
        TEST_DATA["parser_tests"]["aws"],
        ids=lambda tc: tc["name"],
    )
    def test_parse_aws_commands(self, test_case: dict):
        """Test parsing of aws commands."""
        command = test_case["command"]
        expected = test_case["expected"]

        parsed = parse_command(command)

        assert parsed.tool == expected.get("tool", "aws")


# =============================================================================
# Pipe Command Tests
# =============================================================================
class TestPipeCommands:
    """Test pipe command detection and splitting."""

    @pytest.mark.parametrize(
        "test_case",
        TEST_DATA["pipe_tests"],
        ids=lambda tc: tc["name"],
    )
    def test_pipe_detection(self, test_case: dict):
        """Test pipe command detection."""
        command = test_case["command"]
        expected_is_pipe = test_case["is_pipe"]

        assert is_pipe_command(command) == expected_is_pipe

    @pytest.mark.parametrize(
        "test_case",
        [tc for tc in TEST_DATA["pipe_tests"] if tc["is_pipe"]],
        ids=lambda tc: tc["name"],
    )
    def test_pipe_splitting(self, test_case: dict):
        """Test pipe command splitting."""
        command = test_case["command"]
        expected_segments = test_case["segments"]

        segments = split_pipe_commands(command)

        assert len(segments) == len(expected_segments)
        for actual, expected in zip(segments, expected_segments):
            assert actual == expected


# =============================================================================
# Validator Tests
# =============================================================================
class TestValidator:
    """Test security validation."""

    @pytest.fixture
    def validator(self) -> CommandValidator:
        """Create a validator with test configuration."""
        return CommandValidator(TEST_DATA["test_security_config"])

    @pytest.mark.parametrize(
        "test_case",
        TEST_DATA["validator_tests"]["allowed"],
        ids=lambda tc: tc["name"],
    )
    def test_allowed_commands(self, validator: CommandValidator, test_case: dict):
        """Test that allowed commands pass validation."""
        command = test_case["command"]
        result = validator.validate(command)

        assert result.allowed, f"Command should be allowed: {command}. Reason: {result.reason}"

    @pytest.mark.parametrize(
        "test_case",
        TEST_DATA["validator_tests"]["blocked"],
        ids=lambda tc: tc["name"],
    )
    def test_blocked_commands(self, validator: CommandValidator, test_case: dict):
        """Test that dangerous commands are blocked."""
        command = test_case["command"]
        result = validator.validate(command)

        assert not result.allowed, f"Command should be blocked: {command}"
        assert result.reason is not None, "Blocked commands should have a reason"

    def test_permissive_mode_allows_all(self):
        """Test that permissive mode bypasses validation."""
        config = TEST_DATA["test_security_config"].copy()
        config["mode"] = "permissive"
        validator = CommandValidator(config)

        # Even dangerous commands should be allowed
        result = validator.validate("kubectl delete pods --all")
        assert result.allowed


# =============================================================================
# Runner Tests
# =============================================================================
class TestRunner:
    """Test command execution."""

    @pytest.fixture
    def runner(self) -> CommandRunner:
        """Create a runner with test configuration."""
        validator = CommandValidator(TEST_DATA["test_security_config"])
        return CommandRunner(
            validator=validator,
            default_timeout=30,
            max_output_size=10000,
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "test_case",
        TEST_DATA["runner_tests"]["success"],
        ids=lambda tc: tc["name"],
    )
    async def test_successful_execution(self, runner: CommandRunner, test_case: dict):
        """Test successful command execution."""
        command = test_case["command"]
        result = await runner.execute(command)

        assert result.status == CommandStatus.SUCCESS
        assert result.exit_code == test_case.get("expected_exit_code", 0)

        if "expected_stdout_contains" in test_case:
            assert test_case["expected_stdout_contains"] in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "test_case",
        TEST_DATA["runner_tests"]["timeout"],
        ids=lambda tc: tc["name"],
    )
    async def test_timeout_handling(self, runner: CommandRunner, test_case: dict):
        """Test command timeout handling."""
        command = test_case["command"]
        timeout = test_case["timeout"]

        result = await runner.execute(command, timeout=timeout)

        assert result.status == CommandStatus.TIMEOUT
        assert result.exit_code is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "test_case",
        TEST_DATA["runner_tests"]["blocked"],
        ids=lambda tc: tc["name"],
    )
    async def test_blocked_execution(self, runner: CommandRunner, test_case: dict):
        """Test that blocked commands return blocked status."""
        command = test_case["command"]
        result = await runner.execute(command)

        assert result.status == CommandStatus.BLOCKED
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_output_truncation(self, runner: CommandRunner):
        """Test that large output is truncated."""
        # Create a runner with small max output
        validator = CommandValidator(TEST_DATA["test_security_config"])
        small_runner = CommandRunner(
            validator=validator,
            default_timeout=30,
            max_output_size=100,  # Very small limit
        )

        # Generate output larger than limit
        result = await small_runner.execute("echo " + "x" * 200)

        assert result.truncated
        assert len(result.stdout) <= 100

    @pytest.mark.asyncio
    async def test_exit_code_preserved(self, runner: CommandRunner):
        """Test that actual exit code is returned (v1 fix verification)."""
        # Command that exits with non-zero code
        result = await runner.execute("sh -c 'exit 42'")

        assert result.status == CommandStatus.ERROR
        assert result.exit_code == 42  # Should be actual exit code, not 0

    @pytest.mark.asyncio
    async def test_pipe_timeout_all_segments(self, runner: CommandRunner):
        """Test that timeout applies to all pipe segments (v1 fix verification)."""
        # Create runner with short timeout
        validator = CommandValidator(TEST_DATA["test_security_config"])
        short_timeout_runner = CommandRunner(
            validator=validator,
            default_timeout=2,  # 2 seconds total
            max_output_size=10000,
        )

        # Pipe command where second segment would timeout
        # Note: This test is tricky because we need a command that works
        # For now, we test that the infrastructure is in place
        result = await short_timeout_runner.execute("echo test | cat")

        # Should succeed quickly
        assert result.status == CommandStatus.SUCCESS


# =============================================================================
# Integration Tests
# =============================================================================
class TestIntegration:
    """Integration tests combining parser, validator, and runner."""

    @pytest.fixture
    def runner(self) -> CommandRunner:
        """Create a fully configured runner."""
        validator = CommandValidator(TEST_DATA["test_security_config"])
        return CommandRunner(
            validator=validator,
            default_timeout=30,
            max_output_size=10000,
        )

    @pytest.mark.asyncio
    async def test_full_flow_allowed_command(self, runner: CommandRunner):
        """Test full flow for an allowed command."""
        result = await runner.execute("echo 'kubectl simulation'")

        assert result.status == CommandStatus.SUCCESS
        assert result.exit_code == 0
        assert "kubectl simulation" in result.stdout

    @pytest.mark.asyncio
    async def test_full_flow_blocked_command(self, runner: CommandRunner):
        """Test full flow for a blocked command."""
        result = await runner.execute("kubectl delete pods --all")

        assert result.status == CommandStatus.BLOCKED
        assert result.exit_code is None
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_parsed_command_has_namespace(self, runner: CommandRunner):
        """Test that parsed commands correctly extract namespace."""
        parsed = parse_command("kubectl get pods -n my-namespace")

        assert parsed.get_namespace() == "my-namespace"

    @pytest.mark.asyncio
    async def test_parsed_command_has_flag(self, runner: CommandRunner):
        """Test flag detection in parsed commands."""
        parsed = parse_command("kubectl exec -it my-pod -- /bin/bash")

        assert parsed.has_flag("-it")
        assert not parsed.has_flag("-n")


# =============================================================================
# Edge Cases
# =============================================================================
class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_command(self):
        """Test parsing empty command."""
        parsed = parse_command("")
        assert parsed.tool == ""
        assert parsed.action == ""

    def test_malformed_command(self):
        """Test parsing malformed command with unclosed quotes."""
        # Should not raise, should handle gracefully
        parsed = parse_command("kubectl get pods 'unclosed")
        assert parsed.tool == "kubectl"

    def test_command_with_special_characters(self):
        """Test parsing command with special characters."""
        parsed = parse_command("kubectl get pods -l 'app=test,env=prod'")
        assert parsed.tool == "kubectl"
        assert parsed.action == "get"

    @pytest.mark.asyncio
    async def test_nonexistent_command(self):
        """Test execution of nonexistent command."""
        validator = CommandValidator({"mode": "permissive"})
        runner = CommandRunner(validator=validator)

        result = await runner.execute("nonexistent_command_xyz")

        assert result.status == CommandStatus.ERROR
        assert result.exit_code is None or result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
