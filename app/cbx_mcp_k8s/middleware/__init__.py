"""
MCP Middleware for request preprocessing.

Contains:
- ToolCallPreprocessor: Filters unexpected parameters from tool calls
"""

from cbx_mcp_k8s.middleware.preprocessor import (
    ToolCallPreprocessor,
    create_preprocessor,
)

__all__ = [
    "ToolCallPreprocessor",
    "create_preprocessor",
]
