"""
Security validation for CLI commands.

This module implements three-layer security validation:
1. Prefix-based dangerous command blocking
2. Safe pattern overrides for specific allowed forms
3. Regex-based advanced pattern matching

The validator uses structured command parsing for more precise
validation compared to simple string prefix matching.
"""

import re
from typing import Any

from cbx_mcp_k8s.executor.parser import (
    ParsedCommand,
    is_pipe_command,
    parse_command,
    split_pipe_commands,
)
from cbx_mcp_k8s.executor.types import ValidationResult


class CommandValidator:
    """
    Validates commands against security policies.

    This class is initialized with security configuration and provides
    methods to validate commands before execution.
    """

    def __init__(self, security_config: dict[str, Any]):
        """
        Initialize validator with security configuration.

        Args:
            security_config: Security configuration dict containing:
                - mode: "strict" or "permissive"
                - dangerous_commands: dict of tool -> list of blocked prefixes
                - safe_patterns: dict of tool -> list of allowed patterns
                - regex_rules: dict of tool -> list of regex rules
                - allowed_unix_commands: list of allowed unix commands in pipes
        """
        self.mode = security_config.get("mode", "strict")
        self.dangerous_commands = security_config.get("dangerous_commands", {})
        self.safe_patterns = security_config.get("safe_patterns", {})
        self.regex_rules = security_config.get("regex_rules", {})
        self.allowed_unix_commands = set(
            security_config.get("allowed_unix_commands", [])
        )

        # Compile regex patterns for performance
        self._compiled_regex: dict[str, list[tuple[re.Pattern, str, str]]] = {}
        self._compile_regex_rules()

    def _compile_regex_rules(self) -> None:
        """Pre-compile regex patterns for each tool."""
        for tool, rules in self.regex_rules.items():
            self._compiled_regex[tool] = []
            for rule in rules:
                pattern = rule.get("pattern", "")
                action = rule.get("action", "block")
                message = rule.get("message", "Command blocked by regex rule")
                try:
                    compiled = re.compile(pattern)
                    self._compiled_regex[tool].append((compiled, action, message))
                except re.error as e:
                    # Log warning but don't fail - skip invalid patterns
                    print(f"Warning: Invalid regex pattern '{pattern}': {e}")

    def validate(self, command: str) -> ValidationResult:
        """
        Validate a command against security policies.

        Args:
            command: The raw command string to validate

        Returns:
            ValidationResult indicating if command is allowed
        """
        # Permissive mode bypasses all validation
        if self.mode == "permissive":
            return ValidationResult.allow()

        # Handle piped commands
        if is_pipe_command(command):
            return self._validate_pipe_command(command)

        # Parse and validate single command
        parsed = parse_command(command)
        return self._validate_parsed_command(parsed)

    def _validate_pipe_command(self, command: str) -> ValidationResult:
        """Validate a piped command chain."""
        commands = split_pipe_commands(command)

        for i, cmd in enumerate(commands):
            cmd = cmd.strip()
            if not cmd:
                continue

            parsed = parse_command(cmd)

            # First command must be a supported CLI tool
            if i == 0:
                result = self._validate_parsed_command(parsed)
                if not result.allowed:
                    return result
            else:
                # Subsequent commands must be allowed unix commands
                if parsed.tool not in self.allowed_unix_commands:
                    return ValidationResult.block(
                        f"Unix command '{parsed.tool}' is not allowed in pipes",
                        rule="allowed_unix_commands",
                    )

        return ValidationResult.allow()

    def _validate_parsed_command(self, parsed: ParsedCommand) -> ValidationResult:
        """Validate a parsed command."""
        tool = parsed.tool

        # Check if tool is known
        if tool not in self.dangerous_commands and tool not in self.safe_patterns:
            # Unknown tool - allow by default (could be changed to block)
            return ValidationResult.allow()

        # Layer 1: Check dangerous command prefixes
        dangerous_prefixes = self.dangerous_commands.get(tool, [])
        is_dangerous = False
        matched_prefix = None

        for prefix in dangerous_prefixes:
            if parsed.raw.lower().startswith(prefix.lower()):
                is_dangerous = True
                matched_prefix = prefix
                break

        if not is_dangerous:
            # Not a dangerous command - check regex rules and allow
            return self._check_regex_rules(parsed)

        # Layer 2: Check safe pattern overrides
        safe_patterns = self.safe_patterns.get(tool, [])
        for pattern in safe_patterns:
            if self._matches_safe_pattern(parsed, pattern):
                # Matches a safe pattern - check regex and allow
                return self._check_regex_rules(parsed)

        # Command is dangerous and doesn't match safe patterns
        return ValidationResult.block(
            f"Command blocked: matches dangerous pattern '{matched_prefix}'",
            rule=f"dangerous_commands.{tool}",
        )

    def _matches_safe_pattern(self, parsed: ParsedCommand, pattern: str) -> bool:
        """
        Check if parsed command matches a safe pattern.

        Safe patterns can be:
        - Simple prefix: "kubectl delete pod" (requires resource name to follow)
        - With flags: "kubectl exec --help"
        - Interactive: "kubectl exec -it"

        Note: Pattern matching is word-boundary aware to prevent
        "kubectl delete pods" from matching "kubectl delete pod".

        For destructive patterns (delete, etc.), a resource name is required.
        """
        raw_lower = parsed.raw.lower()
        pattern_lower = pattern.lower()

        # Word-boundary aware prefix match
        # Pattern must match at word boundary (space or end of string)
        if raw_lower.startswith(pattern_lower):
            # Check if pattern ends at word boundary
            remaining = raw_lower[len(pattern_lower):]
            if remaining and remaining[0] in (" ", "\t"):
                # There's more content after the pattern - this is good
                # e.g., "kubectl delete pod nginx-pod" matches "kubectl delete pod"
                return True
            elif not remaining:
                # Pattern matches exactly, no resource name provided
                # For destructive actions, require a resource name
                pattern_parsed = parse_command(pattern)
                if pattern_parsed.action in {"delete", "drain", "cordon", "taint"}:
                    return False  # Destructive action without resource name
                return True

        # Check for flag-based patterns (structured matching)
        pattern_parsed = parse_command(pattern)

        # Tool and action must match
        if parsed.tool != pattern_parsed.tool:
            return False
        if parsed.action != pattern_parsed.action:
            return False

        # Check required flags from pattern
        for flag in pattern_parsed.flags:
            if not parsed.has_flag(flag):
                return False

        # Check required resource (exact match, not prefix)
        if pattern_parsed.resource:
            if parsed.resource != pattern_parsed.resource:
                return False
            # For destructive actions with resource type, require a name
            if pattern_parsed.action in {"delete", "drain", "cordon", "taint"}:
                if not parsed.name:
                    return False

        return True

    def _check_regex_rules(self, parsed: ParsedCommand) -> ValidationResult:
        """
        Layer 3: Check command against regex rules.
        """
        tool = parsed.tool
        rules = self._compiled_regex.get(tool, [])

        for pattern, action, message in rules:
            if pattern.search(parsed.raw):
                if action == "block":
                    return ValidationResult.block(message, rule=f"regex_rules.{tool}")
                # action == "allow" - continue checking other rules

        return ValidationResult.allow()

    def validate_exec_command(self, parsed: ParsedCommand) -> ValidationResult:
        """
        Special validation for kubectl exec commands.

        kubectl exec is potentially dangerous as it can spawn interactive shells.
        This method applies additional checks:
        - Block bare shell invocations (sh, bash, etc.) without -c flag
        - Allow explicit interactive mode (-it, -ti)
        - Allow help commands
        """
        if parsed.tool != "kubectl" or parsed.action != "exec":
            return ValidationResult.allow()

        # Always allow help
        if parsed.has_flag("--help"):
            return ValidationResult.allow()

        # Check for interactive flags - explicit user intent
        if parsed.has_flag("-it", "-ti", "-i", "-t"):
            return ValidationResult.allow()

        # Check args for shell invocation
        dangerous_shells = {"sh", "bash", "/bin/sh", "/bin/bash", "/bin/zsh", "zsh"}

        # Look for -- separator and what follows
        try:
            separator_idx = parsed.args.index("--")
            shell_args = parsed.args[separator_idx + 1 :]

            if shell_args:
                first_arg = shell_args[0]
                # If running a shell without -c, it's interactive and dangerous
                if first_arg in dangerous_shells:
                    # Check if there's a -c flag for the shell
                    if "-c" not in shell_args:
                        return ValidationResult.block(
                            "Interactive shell in exec without explicit -it flag is blocked",
                            rule="exec_shell_check",
                        )
        except ValueError:
            # No -- separator, check raw args
            pass

        return ValidationResult.allow()


def create_validator(security_config: dict[str, Any]) -> CommandValidator:
    """
    Factory function to create a CommandValidator.

    Args:
        security_config: Security configuration dictionary

    Returns:
        Configured CommandValidator instance
    """
    return CommandValidator(security_config)
