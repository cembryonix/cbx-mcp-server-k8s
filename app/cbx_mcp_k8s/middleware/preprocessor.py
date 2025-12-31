"""
Tool Call Preprocessor Middleware.

Filters unexpected parameters from tool calls to ensure MCP protocol compliance.
This handles non-standard MCP clients (like n8n) that add extra fields.
"""

import sys

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext, ToolResult


class ToolCallPreprocessor(Middleware):
    """
    Preprocess tool call arguments to ensure MCP protocol compliance.

    This middleware uses WHITELIST-based filtering: it retrieves each tool's
    parameter schema and removes any arguments that are NOT declared in the schema.
    This handles non-standard MCP clients (like n8n) that add extra fields.

    How it works:
    1. Intercepts tool calls via on_call_tool() hook
    2. Fetches the tool definition from FastMCP context
    3. Extracts allowed parameters from tool.parameters['properties']
    4. Filters arguments to ONLY keep whitelisted parameters
    5. Passes cleaned arguments to Pydantic validation

    Example:
        Incoming: {"command": "kubectl get ns", "toolCallId": "call_xxx"}
        Schema allows: ["command", "timeout"]
        Outgoing: {"command": "kubectl get ns"}  # toolCallId removed

    This runs BEFORE Pydantic validation, preventing ValidationError for
    unexpected fields.
    """

    def __init__(self, verbose: bool = False):
        """
        Initialize preprocessor.

        Args:
            verbose: If True, log filtered fields to stderr
        """
        self.verbose = verbose

    async def on_call_tool(
        self,
        context: MiddlewareContext,
        call_next: CallNext,
    ) -> ToolResult:
        """
        Preprocess tool arguments by filtering to schema-defined parameters.

        Args:
            context: Middleware context containing the tool call message
            call_next: Function to call next middleware/handler in chain

        Returns:
            Result from the tool execution
        """
        await self._filter_to_schema(context)
        return await call_next(context)

    async def _filter_to_schema(self, context: MiddlewareContext) -> None:
        """
        Filter arguments to ONLY keep parameters defined in the tool's schema.

        Args:
            context: Middleware context with message data
        """
        # For on_call_tool, context.message is CallToolRequestParams directly
        # It has 'name' and 'arguments' attributes
        message = context.message
        if not hasattr(message, "arguments") or not message.arguments:
            return

        tool_name = message.name
        original_args = dict(message.arguments)

        # Get the tool definition using FastMCP API
        try:
            fastmcp = context.fastmcp
            tool = await fastmcp.get_tool(tool_name)
        except Exception as e:
            if self.verbose:
                print(
                    f"[Preprocessor] Could not retrieve tool '{tool_name}': {e}",
                    file=sys.stderr,
                )
            return

        # Extract allowed parameters from the tool's input schema
        allowed_params = self._extract_allowed_params(tool.parameters, tool_name)

        if allowed_params is None:
            return

        # Filter: ONLY keep parameters that are in the schema (whitelist)
        filtered_args = {
            key: value for key, value in original_args.items() if key in allowed_params
        }

        # Log what was filtered
        removed_fields = set(original_args.keys()) - set(filtered_args.keys())
        if removed_fields and self.verbose:
            print(
                f"[Preprocessor] Tool '{tool_name}': filtered {removed_fields}",
                file=sys.stderr,
            )

        # Replace with filtered arguments
        # Note: message.arguments might be a dict or similar mutable structure
        if hasattr(message, "arguments") and message.arguments is not None:
            # Update arguments in place
            message.arguments.clear()
            message.arguments.update(filtered_args)

    def _extract_allowed_params(
        self, schema: dict, tool_name: str
    ) -> set[str] | None:
        """
        Extract the set of allowed parameter names from a JSON Schema.

        Args:
            schema: JSON Schema object
            tool_name: Tool name for logging

        Returns:
            Set of allowed parameter names, or None if schema is malformed
        """
        if not isinstance(schema, dict):
            if self.verbose:
                print(
                    f"[Preprocessor] Tool '{tool_name}' has non-dict schema",
                    file=sys.stderr,
                )
            return None

        if "properties" not in schema:
            if self.verbose:
                print(
                    f"[Preprocessor] Tool '{tool_name}' schema missing 'properties'",
                    file=sys.stderr,
                )
            return None

        properties = schema["properties"]

        if not isinstance(properties, dict):
            if self.verbose:
                print(
                    f"[Preprocessor] Tool '{tool_name}' properties not a dict",
                    file=sys.stderr,
                )
            return None

        return set(properties.keys())


def create_preprocessor(verbose: bool = False) -> ToolCallPreprocessor:
    """
    Factory function to create a ToolCallPreprocessor.

    Args:
        verbose: If True, log filtered fields

    Returns:
        Configured ToolCallPreprocessor instance
    """
    return ToolCallPreprocessor(verbose=verbose)
