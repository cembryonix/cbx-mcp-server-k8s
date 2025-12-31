"""
Structured command parsing.

This module parses CLI command strings into structured ParsedCommand objects,
enabling more precise security validation than simple string prefix matching.
"""

import shlex
from typing import Optional

from cbx_mcp_k8s.executor.types import ParsedCommand


# Known CLI tools and their typical command structures
SUPPORTED_TOOLS = {"kubectl", "helm", "argocd", "aws"}

# kubectl actions that take a resource type
KUBECTL_RESOURCE_ACTIONS = {
    "get", "describe", "delete", "create", "apply", "patch", "edit",
    "label", "annotate", "scale", "rollout", "expose", "autoscale",
    "logs", "exec", "cp", "port-forward", "attach", "debug",
}

# helm subcommands
HELM_ACTIONS = {
    "install", "upgrade", "uninstall", "delete", "list", "status",
    "history", "rollback", "repo", "search", "show", "template",
    "lint", "package", "pull", "push", "plugin", "env", "version",
}

# argocd app subcommands
ARGOCD_APP_ACTIONS = {
    "list", "get", "create", "set", "delete", "sync", "wait",
    "terminate-op", "rollback", "history", "manifests", "diff",
    "actions", "logs", "resources",
}


def parse_command(command: str) -> ParsedCommand:
    """
    Parse a command string into a structured ParsedCommand.

    Args:
        command: The raw command string

    Returns:
        ParsedCommand with parsed components

    Examples:
        >>> parse_command("kubectl get pods -n default")
        ParsedCommand(tool='kubectl', action='get', resource='pod', ...)

        >>> parse_command("helm install myrelease ./chart --namespace prod")
        ParsedCommand(tool='helm', action='install', ...)
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        # Handle malformed commands (unclosed quotes, etc.)
        tokens = command.split()

    if not tokens:
        return ParsedCommand(tool="", action="", raw=command)

    tool = tokens[0].lower()
    remaining = tokens[1:]

    if tool == "kubectl":
        return _parse_kubectl(remaining, command)
    elif tool == "helm":
        return _parse_helm(remaining, command)
    elif tool == "argocd":
        return _parse_argocd(remaining, command)
    elif tool == "aws":
        return _parse_aws(remaining, command)
    else:
        # Unknown tool - basic parsing
        return _parse_generic(tool, remaining, command)


def _parse_kubectl(tokens: list[str], raw: str) -> ParsedCommand:
    """Parse kubectl command."""
    if not tokens:
        return ParsedCommand(tool="kubectl", action="", raw=raw)

    action = tokens[0]
    args: list[str] = []
    flags: dict[str, Optional[str]] = {}
    resource: Optional[str] = None
    name: Optional[str] = None

    i = 1
    while i < len(tokens):
        token = tokens[i]

        if token.startswith("--"):
            # Long flag
            if "=" in token:
                key, value = token.split("=", 1)
                flags[key] = value
            elif i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                flags[token] = tokens[i + 1]
                i += 1
            else:
                flags[token] = None
        elif token.startswith("-") and len(token) == 2:
            # Short flag
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                flags[token] = tokens[i + 1]
                i += 1
            else:
                flags[token] = None
        elif token.startswith("-") and len(token) > 2:
            # Combined short flags like -it or -ti
            flags[token] = None
        else:
            # Positional argument
            args.append(token)

        i += 1

    # For resource-based actions, first arg is typically the resource type
    if action in KUBECTL_RESOURCE_ACTIONS and args:
        resource = _normalize_resource_type(args[0])
        if len(args) > 1:
            # Could be resource name or resource/name format
            if "/" in args[0]:
                # Format: type/name
                parts = args[0].split("/", 1)
                resource = _normalize_resource_type(parts[0])
                name = parts[1]
            else:
                name = args[1] if len(args) > 1 else None

    return ParsedCommand(
        tool="kubectl",
        action=action,
        resource=resource,
        name=name,
        args=args,
        flags=flags,
        raw=raw,
    )


def _parse_helm(tokens: list[str], raw: str) -> ParsedCommand:
    """Parse helm command."""
    if not tokens:
        return ParsedCommand(tool="helm", action="", raw=raw)

    action = tokens[0]
    args: list[str] = []
    flags: dict[str, Optional[str]] = {}
    name: Optional[str] = None

    i = 1
    while i < len(tokens):
        token = tokens[i]

        if token.startswith("--"):
            if "=" in token:
                key, value = token.split("=", 1)
                flags[key] = value
            elif i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                flags[token] = tokens[i + 1]
                i += 1
            else:
                flags[token] = None
        elif token.startswith("-") and len(token) == 2:
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                flags[token] = tokens[i + 1]
                i += 1
            else:
                flags[token] = None
        else:
            args.append(token)

        i += 1

    # For install/upgrade, first arg is release name
    if action in {"install", "upgrade", "uninstall", "delete", "status", "history"} and args:
        name = args[0]

    return ParsedCommand(
        tool="helm",
        action=action,
        name=name,
        args=args,
        flags=flags,
        raw=raw,
    )


def _parse_argocd(tokens: list[str], raw: str) -> ParsedCommand:
    """Parse argocd command."""
    if not tokens:
        return ParsedCommand(tool="argocd", action="", raw=raw)

    # argocd commands are typically: argocd <resource> <action> [args]
    # e.g., argocd app list, argocd app sync myapp
    resource = tokens[0] if tokens else ""
    action = tokens[1] if len(tokens) > 1 else ""

    args: list[str] = []
    flags: dict[str, Optional[str]] = {}
    name: Optional[str] = None

    i = 2
    while i < len(tokens):
        token = tokens[i]

        if token.startswith("--"):
            if "=" in token:
                key, value = token.split("=", 1)
                flags[key] = value
            elif i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                flags[token] = tokens[i + 1]
                i += 1
            else:
                flags[token] = None
        elif token.startswith("-") and len(token) == 2:
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                flags[token] = tokens[i + 1]
                i += 1
            else:
                flags[token] = None
        else:
            args.append(token)

        i += 1

    # First positional arg after resource/action is typically the app name
    if args:
        name = args[0]

    return ParsedCommand(
        tool="argocd",
        action=f"{resource} {action}".strip(),
        resource=resource,
        name=name,
        args=args,
        flags=flags,
        raw=raw,
    )


def _parse_aws(tokens: list[str], raw: str) -> ParsedCommand:
    """Parse aws command."""
    if not tokens:
        return ParsedCommand(tool="aws", action="", raw=raw)

    # aws commands: aws <service> <action> [args]
    # e.g., aws ec2 describe-instances, aws eks list-clusters
    service = tokens[0] if tokens else ""
    action = tokens[1] if len(tokens) > 1 else ""

    args: list[str] = []
    flags: dict[str, Optional[str]] = {}

    i = 2
    while i < len(tokens):
        token = tokens[i]

        if token.startswith("--"):
            if "=" in token:
                key, value = token.split("=", 1)
                flags[key] = value
            elif i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                flags[token] = tokens[i + 1]
                i += 1
            else:
                flags[token] = None
        else:
            args.append(token)

        i += 1

    return ParsedCommand(
        tool="aws",
        action=f"{service} {action}".strip(),
        resource=service,
        args=args,
        flags=flags,
        raw=raw,
    )


def _parse_generic(tool: str, tokens: list[str], raw: str) -> ParsedCommand:
    """Parse unknown tool command with basic structure."""
    action = tokens[0] if tokens else ""
    args = tokens[1:] if len(tokens) > 1 else []

    return ParsedCommand(
        tool=tool,
        action=action,
        args=args,
        flags={},
        raw=raw,
    )


def _normalize_resource_type(resource: str) -> str:
    """
    Normalize Kubernetes resource type to singular form.

    Examples:
        pods -> pod
        deployments -> deployment
        svc -> service
    """
    # Handle common aliases
    aliases = {
        "po": "pod",
        "pods": "pod",
        "svc": "service",
        "services": "service",
        "deploy": "deployment",
        "deployments": "deployment",
        "rs": "replicaset",
        "replicasets": "replicaset",
        "ds": "daemonset",
        "daemonsets": "daemonset",
        "sts": "statefulset",
        "statefulsets": "statefulset",
        "cm": "configmap",
        "configmaps": "configmap",
        "ns": "namespace",
        "namespaces": "namespace",
        "no": "node",
        "nodes": "node",
        "pv": "persistentvolume",
        "persistentvolumes": "persistentvolume",
        "pvc": "persistentvolumeclaim",
        "persistentvolumeclaims": "persistentvolumeclaim",
        "ing": "ingress",
        "ingresses": "ingress",
        "netpol": "networkpolicy",
        "networkpolicies": "networkpolicy",
        "sa": "serviceaccount",
        "serviceaccounts": "serviceaccount",
        "hpa": "horizontalpodautoscaler",
        "horizontalpodautoscalers": "horizontalpodautoscaler",
        "cj": "cronjob",
        "cronjobs": "cronjob",
        "jobs": "job",
        "secrets": "secret",
        "ep": "endpoints",
        "endpoints": "endpoints",
        "ev": "event",
        "events": "event",
    }

    resource_lower = resource.lower()
    return aliases.get(resource_lower, resource_lower)


def is_pipe_command(command: str) -> bool:
    """
    Check if command contains pipe operators.

    Note: This is a simple check that doesn't account for
    quoted pipe characters.
    """
    # Check for unquoted pipe
    in_single_quote = False
    in_double_quote = False

    for i, char in enumerate(command):
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == "|" and not in_single_quote and not in_double_quote:
            return True

    return False


def split_pipe_commands(command: str) -> list[str]:
    """
    Split a piped command into individual commands.

    Returns list of individual commands to execute in sequence.
    """
    commands: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False

    for char in command:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(char)
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(char)
        elif char == "|" and not in_single_quote and not in_double_quote:
            commands.append("".join(current).strip())
            current = []
        else:
            current.append(char)

    # Add the last command
    if current:
        commands.append("".join(current).strip())

    return [c for c in commands if c]  # Filter empty strings
