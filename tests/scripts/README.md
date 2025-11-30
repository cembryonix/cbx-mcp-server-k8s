# Test Scripts

This directory contains scripts for starting and testing the MCP server.

## Section 1: Starting MCP Server

Scripts to start the MCP server in different configurations for development and testing.

### start-stdio.sh - Local Development (stdio transport)

Starts the server with stdio transport, suitable for Claude Desktop integration.

```bash
# Default configuration
./start-stdio.sh

# With specific config
./start-stdio.sh --config-name stdio
```

### start-http.sh - HTTP Transport

Starts the server with HTTP transport on port 8080.

```bash
# Default HTTP configuration
./start-http.sh

# With specific config
./start-http.sh --config-name http
```

**Server endpoint:** `http://127.0.0.1:8080/mcp`

### start-docker.sh - Docker Container

Runs the MCP server in a Docker container with HTTP transport.

```bash
./start-docker.sh
```

**Prerequisites:**
- Docker installed
- Image built: `cbx-mcp-server-k8s:develop`
- Kubernetes config at `~/.kube/`

**Mounts:**
- `~/.kube` - Kubernetes configuration (read-only)
- `~/.config/argocd` - ArgoCD configuration (read-only)

### test-docker-stdio.sh - Docker stdio Test

Quick test to verify Docker container responds to MCP initialization.

```bash
./test-docker-stdio.sh [image_name]

# Examples:
./test-docker-stdio.sh                           # Uses default image
./test-docker-stdio.sh cbx-mcp-server-k8s:v1.0   # Specific image
```

---

## Section 2: MCP Server Ad Hoc Testing

The `capability_audit.py` script provides ad-hoc capability testing to see what MCP features are implemented.

### Quick Start

Test your running server:
```bash
python capability_audit.py --server-url http://127.0.0.1:8080/mcp --transport streamable_http
```

Test with custom configuration file:
```bash
python capability_audit.py --config my_server_config.json
```

Save detailed results to file:
```bash
python capability_audit.py --server-url http://127.0.0.1:8080/mcp --output test_results.json
```

### Command Line Options

```bash
python capability_audit.py [OPTIONS]

Options:
  --server-url TEXT     MCP server URL (default: http://127.0.0.1:8080/mcp)
  --transport TEXT      Transport type (default: streamable_http)
  --config FILE         JSON config file for server connection
  --output FILE         Save results to JSON file
  --help               Show this message and exit
```

### Configuration Files

**HTTP Transport:**
```json
{
  "url": "http://127.0.0.1:8080/mcp",
  "transport": "streamable_http",
  "timeout": 30
}
```

**Local Development:**
```json
{
  "url": "http://localhost:8000/mcp",
  "transport": "streamable_http",
  "name": "dev-server"
}
```

### Expected Output

```
MCP Server Ad Hoc Capability Testing
Server: {'url': 'http://127.0.0.1:8080/mcp', 'transport': 'streamable_http'}

Starting MCP Server Capability Tests
============================================================
Testing basic connection...
  Implemented Basic Connection: Server responsive, found 6 tools

Testing tools listing...
  Implemented Tools Listing: All 6 expected tools found

Testing tool execution...
  Implemented kubectl Execute Tool: Command executed successfully
  Implemented helm Execute Tool: Command executed successfully
  ...

Testing resources support...
  Not Implemented Resources Support: Resources not implemented on server

============================================================
MCP SERVER CAPABILITY SUMMARY
============================================================

IMPLEMENTED (8):
  * Basic Connection
  * Tools Listing
  * kubectl Execute Tool
  * kubectl Describe Tool
  * helm Execute Tool
  * helm Describe Tool

NOT IMPLEMENTED (3):
  * Resources Support
  * Prompts Support
  * Server Sampling

IMPLEMENTATION STATUS: 58.3% complete
```

### Status Icons Guide

| Icon | Status | Meaning |
|------|--------|---------|
| Implemented | Feature is working correctly |
| Partially Implemented | Feature works but has issues |
| Not Implemented | Feature is missing |
| Error | Feature is broken/failing |
| Unknown | Cannot determine status |

### Development Workflow

```bash
# 1. Start the server
./start-http.sh

# 2. Run capability audit (in another terminal)
python capability_audit.py --server-url http://127.0.0.1:8080/mcp

# 3. Save results for comparison
python capability_audit.py --output results_v1.json
```

### JSON Output Format

When using `--output`, results are saved as:
```json
{
  "server_config": {
    "url": "http://127.0.0.1:8080/mcp",
    "transport": "streamable_http"
  },
  "results": [
    {
      "name": "Basic Connection",
      "status": "Implemented",
      "details": "Server responsive, found 6 tools",
      "data": {"tool_count": 6},
      "error": null
    }
  ],
  "summary": "IMPLEMENTATION STATUS: 58.3% complete"
}
```

### Extending Tests

Add custom capability tests by extending `MCPServerCapabilityTester`:

```python
async def test_custom_capability(self) -> CapabilityResult:
    """Test custom MCP capability"""
    try:
        # Your test logic here
        return CapabilityResult(
            name="Custom Capability",
            status=CapabilityStatus.IMPLEMENTED,
            details="Custom test passed"
        )
    except Exception as e:
        return CapabilityResult(
            name="Custom Capability",
            status=CapabilityStatus.ERROR,
            details="Test failed",
            error=str(e)
        )
```