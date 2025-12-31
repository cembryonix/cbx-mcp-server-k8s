"""
MCP Prompt templates for Kubernetes operations.

Provides prompt templates that help LLMs generate appropriate
kubectl, helm, and argocd commands for common operations.
"""

from cbx_mcp_k8s.prompts.templates import register_prompts

__all__ = [
    "register_prompts",
]
