"""
MCP Resources for Kubernetes Cluster Information.

Provides read-only resources for cluster introspection:
- k8s://cluster/context - Current kubectl context
- k8s://cluster/namespaces - Available namespaces
- k8s://cluster/info - Cluster version and API server info
"""

import asyncio
import json
import subprocess
import sys
from typing import Any

from fastmcp import FastMCP


def register_resources(mcp: FastMCP) -> None:
    """
    Register Kubernetes cluster resources with the MCP server.

    Args:
        mcp: FastMCP server instance
    """
    print("Registering Kubernetes resources...", file=sys.stderr)

    @mcp.resource(
        uri="k8s://cluster/context",
        name="Current Kubernetes Context",
        description="Shows the current kubectl context, cluster, and user",
        mime_type="application/json",
    )
    async def get_current_context() -> str:
        """Get the current kubectl context information."""
        result = await _run_kubectl("config", "view", "--minify", "-o", "json")
        if result["success"]:
            try:
                config = json.loads(result["output"])
                context_info = {
                    "current_context": config.get("current-context", "unknown"),
                    "cluster": _extract_cluster_info(config),
                    "user": _extract_user_info(config),
                }
                return json.dumps(context_info, indent=2)
            except json.JSONDecodeError:
                return json.dumps({"error": "Failed to parse kubectl output"})
        return json.dumps({"error": result.get("error", "Unknown error")})

    @mcp.resource(
        uri="k8s://cluster/namespaces",
        name="Kubernetes Namespaces",
        description="Lists all available namespaces in the cluster",
        mime_type="application/json",
    )
    async def get_namespaces() -> str:
        """Get list of all namespaces."""
        result = await _run_kubectl("get", "namespaces", "-o", "json")
        if result["success"]:
            try:
                data = json.loads(result["output"])
                namespaces = [
                    {
                        "name": ns["metadata"]["name"],
                        "status": ns.get("status", {}).get("phase", "Unknown"),
                    }
                    for ns in data.get("items", [])
                ]
                return json.dumps({"namespaces": namespaces}, indent=2)
            except json.JSONDecodeError:
                return json.dumps({"error": "Failed to parse kubectl output"})
        return json.dumps({"error": result.get("error", "Unknown error")})

    @mcp.resource(
        uri="k8s://cluster/info",
        name="Kubernetes Cluster Info",
        description="Shows cluster version and API server information",
        mime_type="application/json",
    )
    async def get_cluster_info() -> str:
        """Get cluster version and server information."""
        # Get server version
        version_result = await _run_kubectl("version", "-o", "json")

        info: dict[str, Any] = {
            "server_version": None,
            "client_version": None,
            "api_server": None,
        }

        if version_result["success"]:
            try:
                version_data = json.loads(version_result["output"])
                info["server_version"] = version_data.get("serverVersion", {}).get(
                    "gitVersion"
                )
                info["client_version"] = version_data.get("clientVersion", {}).get(
                    "gitVersion"
                )
            except json.JSONDecodeError:
                pass

        # Get cluster endpoint
        config_result = await _run_kubectl("config", "view", "--minify", "-o", "json")
        if config_result["success"]:
            try:
                config = json.loads(config_result["output"])
                clusters = config.get("clusters", [])
                if clusters:
                    info["api_server"] = clusters[0].get("cluster", {}).get("server")
            except json.JSONDecodeError:
                pass

        return json.dumps(info, indent=2)

    print("Registered 3 cluster resources", file=sys.stderr)


async def _run_kubectl(*args: str) -> dict[str, Any]:
    """
    Run a kubectl command asynchronously.

    Args:
        *args: kubectl subcommand and arguments

    Returns:
        Dict with 'success', 'output', and optionally 'error'
    """
    cmd = ["kubectl"] + list(args)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode == 0:
            return {"success": True, "output": stdout.decode()}
        else:
            return {"success": False, "error": stderr.decode()}
    except asyncio.TimeoutError:
        return {"success": False, "error": "Command timed out"}
    except FileNotFoundError:
        return {"success": False, "error": "kubectl not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _extract_cluster_info(config: dict) -> dict[str, Any]:
    """Extract cluster info from kubeconfig."""
    clusters = config.get("clusters", [])
    if clusters:
        cluster = clusters[0].get("cluster", {})
        return {
            "name": clusters[0].get("name", "unknown"),
            "server": cluster.get("server", "unknown"),
        }
    return {"name": "unknown", "server": "unknown"}


def _extract_user_info(config: dict) -> dict[str, Any]:
    """Extract user info from kubeconfig."""
    users = config.get("users", [])
    if users:
        return {"name": users[0].get("name", "unknown")}
    return {"name": "unknown"}
