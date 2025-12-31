# Registering a New CLI Tool

Adding a new CLI tool to the MCP server requires **only configuration changes** - no code modifications needed.

## Step 1: Add to `supported_cli_tools.json`

Edit `app/cbx_mcp_k8s/config/data/supported_cli_tools.json`:

```json
"istioctl": {
  "check_cmd": "istioctl version --remote=false",
  "test_cmd_config": "istioctl version",
  "help_flag": "--help",
  "description": "Istio service mesh CLI",
  "example": "istioctl analyze"
}
```

### Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `check_cmd` | Yes | Command to verify tool is installed |
| `test_cmd_config` | Yes | Command to test tool configuration works |
| `help_flag` | Yes | Flag to get help text (usually `--help`) |
| `description` | Yes | Human-readable description of the tool |
| `example` | Yes | Example command for documentation |

## Step 2 (Optional): Add Security Rules

Edit `app/cbx_mcp_k8s/config/data/default_security_config.yaml`:

```yaml
dangerous_commands:
  istioctl:
    - "istioctl uninstall"
    - "istioctl install"

safe_patterns:
  istioctl:
    - "istioctl analyze"
    - "istioctl proxy-status"
```

### Security Configuration Options

- **`dangerous_commands`**: Commands blocked by default (prefix matching)
- **`safe_patterns`**: Exceptions to dangerous commands (exact or pattern matching)
- **`regex_rules`**: Advanced pattern matching for complex validation

## What Happens Automatically

When the server starts, the following happens without any code changes:

### 1. Tool Registration

The dynamic registration loop in `tools/__init__.py` iterates through `TOOLS_CONFIG` and automatically:
- Creates `describe_istioctl(command, ctx)` function
- Creates `execute_istioctl(command, timeout, ctx)` function
- Registers both with FastMCP including proper annotations

### 2. Schema Generation

Pydantic automatically generates JSON Schema for each tool:

**`describe_istioctl`:**
```json
{
  "type": "object",
  "properties": {
    "command": {"type": "string", "description": "Specific Istioctl command to get help for"}
  }
}
```

**`execute_istioctl`:**
```json
{
  "type": "object",
  "properties": {
    "command": {"type": "string", "description": "Complete Istioctl command to execute"},
    "timeout": {"type": "integer", "description": "Maximum execution time in seconds"}
  },
  "required": ["command"]
}
```

### 3. Middleware Integration

The `ToolCallPreprocessor` middleware automatically:
- Queries the tool's schema at runtime via `get_tool(tool_name)`
- Extracts allowed parameters from `tool.parameters['properties']`
- Filters out any extra parameters sent by non-standard MCP clients (e.g., n8n's `toolCallId`)

### 4. Security Validation

The security validator automatically:
- Applies dangerous command blocking based on `dangerous_commands` config
- Checks safe pattern exceptions from `safe_patterns` config
- Runs regex rules if defined

## Verification

After adding a new tool, verify it works:

```bash
# Start the server
./tests/scripts/start-stdio.sh

# Run validation tests
python tests/validation/validation-mcp-client.py ci \
  --server-cmd "python app/main.py --config-dir tests/server-configs/stdio"
```

The new tool should appear in `tools/list` response and be callable via `tools/call`.