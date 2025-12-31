# middleware/tool_call_preprocessor.py

from fastmcp.server.middleware import Middleware, MiddlewareContext
from ..utils import get_logger

logger = get_logger(__name__)


class ToolCallPreprocessor(Middleware):
    """
    Preprocess tool call arguments to ensure MCP protocol compliance.

    This middleware uses WHITELIST-based filtering: it retrieves each tool's
    parameter schema and removes any arguments that are NOT declared in the schema.
    This handles non-standard MCP clients (like n8n) that add extra fields.

    How it works:
    1. Intercepts tool calls via on_call_tool() hook
    2. Fetches the tool definition: tool = await get_tool(tool_name)
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

    async def on_call_tool(self, context: MiddlewareContext, call_next):
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
        Filter arguments to ONLY keep parameters defined in the tool's schema (whitelist approach).

        This retrieves the tool definition and extracts allowed parameters from tool.parameters
        (the JSON Schema for input). Any arguments not in the schema are removed.

        Args:
            context: Middleware context with message.name and message.arguments
        """

        # Skip if no arguments to filter
        if not hasattr(context.message, 'arguments') or not context.message.arguments:
            logger.debug("No arguments to filter")
            return

        tool_name = context.message.name
        original_args = context.message.arguments.copy()

        # Get the tool definition using official FastMCP API
        try:
            tool = await context.fastmcp_context.fastmcp.get_tool(tool_name)
        except Exception as e:
            logger.warning(
                f"Could not retrieve tool '{tool_name}' to validate arguments: {e}. "
                f"Skipping filtering."
            )
            return

        # Extract allowed parameters from the tool's input schema (tool.parameters)
        allowed_params = self._extract_allowed_params(tool.parameters, tool_name)

        if allowed_params is None:
            # Schema structure issue, skip filtering
            return

        # Filter: ONLY keep parameters that are in the schema (whitelist)
        filtered_args = {
            key: value
            for key, value in original_args.items()
            if key in allowed_params
        }

        # Log what was filtered (for debugging and auditing)
        removed_fields = set(original_args.keys()) - set(filtered_args.keys())
        if removed_fields:
            logger.info(
                f"Tool '{tool_name}': filtered non-schema fields {removed_fields}. "
                f"Original params: {set(original_args.keys())}, "
                f"Filtered params: {set(filtered_args.keys())}, "
                f"Schema allows: {allowed_params}"
            )
        else:
            logger.debug(f"Tool '{tool_name}': no fields filtered (all valid)")

        # Replace with filtered arguments
        context.message.arguments = filtered_args

    def _extract_allowed_params(self, schema: dict, tool_name: str) -> set[str] | None:
        """
        Extract the set of allowed parameter names from a JSON Schema.

        Args:
            schema: JSON Schema object (typically {"type": "object", "properties": {...}})
            tool_name: Tool name for logging

        Returns:
            Set of allowed parameter names, or None if schema is malformed
        """

        # Validate schema structure
        if not isinstance(schema, dict):
            logger.warning(
                f"Tool '{tool_name}' has non-dict schema (type={type(schema)}). "
                f"Skipping filtering."
            )
            return None

        # Check for 'properties' key (standard JSON Schema for objects)
        if 'properties' not in schema:
            logger.warning(
                f"Tool '{tool_name}' schema missing 'properties' key. "
                f"Schema keys: {list(schema.keys())}. Skipping filtering."
            )
            return None

        properties = schema['properties']

        if not isinstance(properties, dict):
            logger.warning(
                f"Tool '{tool_name}' schema 'properties' is not a dict "
                f"(type={type(properties)}). Skipping filtering."
            )
            return None

        # Extract parameter names
        allowed_params = set(properties.keys())

        logger.debug(f"Tool '{tool_name}' schema allows parameters: {allowed_params}")

        return allowed_params