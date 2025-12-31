#!/usr/bin/env python3
"""
Execute commands against MCP server.

Usage:
    ./execute-commands.py -i commands.yaml      # Execute commands from file
    ./execute-commands.py -c "kubectl: get ns"  # Execute single command
    ./execute-commands.py -i commands.yaml -c "kubectl: get pods"  # Both

Input file format (YAML):
    kubectl: get namespaces
    kubectl: get pods -n default | head -5
    helm: list -A

Or as a list:
    - kubectl: get namespaces
    - kubectl: get pods -n default
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml


def load_config() -> dict:
    """Load configuration from config.yaml."""
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        return yaml.safe_load(f)


def parse_command_string(cmd_str: str) -> tuple[str, str]:
    """
    Parse 'tool_name: command' string.

    Returns:
        (tool_name, command)
    """
    if ":" not in cmd_str:
        print(
            f"Error: Invalid command format '{cmd_str}'. Expected 'tool_name: command'",
            file=sys.stderr,
        )
        sys.exit(1)

    parts = cmd_str.split(":", 1)
    tool_name = parts[0].strip()
    command = parts[1].strip()
    return tool_name, command


def load_commands_from_file(file_path: str) -> list[tuple[str, str]]:
    """
    Load commands from YAML file.

    Returns:
        List of (tool_name, command) tuples
    """
    path = Path(file_path)
    if not path.exists():
        print(f"Error: Input file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        data = yaml.safe_load(f)

    commands = []

    if isinstance(data, dict):
        # Format: {tool: command, tool: command}
        for tool, cmd in data.items():
            commands.append((tool, cmd))
    elif isinstance(data, list):
        # Format: [{tool: command}, {tool: command}]
        for item in data:
            if isinstance(item, dict):
                for tool, cmd in item.items():
                    commands.append((tool, cmd))
            elif isinstance(item, str):
                # Format: ["tool: command", "tool: command"]
                commands.append(parse_command_string(item))
    else:
        print("Error: Invalid input file format", file=sys.stderr)
        sys.exit(1)

    return commands


class MCPClient:
    """Simple MCP client for stdio transport."""

    def __init__(self, config: dict):
        self.config = config
        self.process = None
        self.request_id = 0

    def start(self):
        """Start the MCP server process."""
        server_config = self.config["mcp_server"]

        cmd = [
            server_config["python"],
            server_config["main"],
            "--transport", server_config["transport"],
            "--config-dir", server_config["config_dir"],
        ]

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Initialize MCP session
        self._initialize()

    def stop(self):
        """Stop the MCP server process."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def _send_request(self, method: str, params: dict) -> dict:
        """Send JSON-RPC request and get response."""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }

        request_line = json.dumps(request) + "\n"
        self.process.stdin.write(request_line.encode())
        self.process.stdin.flush()

        response_line = self.process.stdout.readline().decode()
        return json.loads(response_line)

    def _initialize(self):
        """Initialize MCP session."""
        response = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "standalone-test", "version": "1.0.0"},
        })

        if "error" in response:
            raise RuntimeError(f"Failed to initialize MCP: {response['error']}")

    def call_tool(self, tool_name: str, command: str, timeout: int = None) -> dict:
        """
        Call an MCP tool.

        Args:
            tool_name: Base tool name (kubectl, helm, argocd)
            command: Command to execute
            timeout: Optional timeout in seconds

        Returns:
            Tool response dict
        """
        # Map tool name to MCP tool name
        mcp_tool_name = f"k8s_{tool_name}_execute"

        arguments = {"command": command}
        if timeout:
            arguments["timeout"] = timeout

        response = self._send_request("tools/call", {
            "name": mcp_tool_name,
            "arguments": arguments,
        })

        return response


def format_result(tool: str, command: str, response: dict) -> str:
    """Format tool response for display."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"Tool: {tool}")
    lines.append(f"Command: {command}")
    lines.append(f"{'-' * 60}")

    if "error" in response:
        lines.append(f"ERROR: {response['error'].get('message', response['error'])}")
    elif "result" in response:
        result = response["result"]
        content = result.get("content", [])
        if content:
            text = content[0].get("text", "")
            lines.append(text)
        else:
            lines.append("(empty response)")
    else:
        lines.append(f"Unexpected response: {response}")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Execute commands against MCP server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-i", "--input",
        help="Input YAML file with commands",
    )
    parser.add_argument(
        "-c", "--command",
        action="append",
        help="Single command in format 'tool_name: command' (can be repeated)",
    )
    parser.add_argument(
        "-t", "--timeout",
        type=int,
        help="Command timeout in seconds (overrides config)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show verbose output",
    )

    args = parser.parse_args()

    # Collect commands
    commands = []

    if args.input:
        commands.extend(load_commands_from_file(args.input))

    if args.command:
        for cmd_str in args.command:
            commands.append(parse_command_string(cmd_str))

    if not commands:
        parser.print_help()
        print("\nError: No commands specified. Use -i or -c.", file=sys.stderr)
        sys.exit(1)

    # Load config
    config = load_config()
    timeout = args.timeout or config.get("default_timeout", 60)

    # Start MCP client
    client = MCPClient(config)

    try:
        if args.verbose:
            print("Starting MCP server...", file=sys.stderr)
        client.start()

        if args.verbose:
            print(f"Executing {len(commands)} command(s)...\n", file=sys.stderr)

        # Execute commands
        for tool, command in commands:
            response = client.call_tool(tool, command, timeout)
            print(format_result(tool, command, response))

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.stop()


if __name__ == "__main__":
    main()
