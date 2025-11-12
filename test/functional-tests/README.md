# MCP Server Ad Hoc Testing - Usage Guide

A simple, direct approach to test MCP server capabilities and see what's implemented vs what needs work.

## Quick Start

### Basic Usage

Test your current server setup:
```bash
python run_mcp_tests.py --server-url http://127.0.0.1:8080/mcp --transport streamable_http
```

Test with custom configuration file:
```bash
python run_mcp_tests.py --config my_server_config.json
```

Save detailed results to file for analysis:
```bash
python run_mcp_tests.py --server-url http://127.0.0.1:8080/mcp --output test_results.json
```

### Transport Options

Test different transport modes:
```bash
# HTTP transport
python run_mcp_tests.py --server-url http://127.0.0.1:8080/mcp --transport streamable_http

# Stdio transport  
python run_mcp_tests.py --server-url stdio://path/to/server.py --transport stdio
```

## Configuration Files

### HTTP Transport Configuration

**File:** `my_server_config.json`
```json
{
  "url": "http://127.0.0.1:8080/mcp",
  "transport": "streamable_http",
  "timeout": 30
}
```

### Local Development Configuration

**File:** `local_dev_config.json`
```json
{
  "url": "http://localhost:8000/mcp", 
  "transport": "streamable_http",
  "name": "dev-server"
}
```

### Stdio Transport Configuration

**File:** `stdio_config.json`
```json
{
  "command": "python",
  "args": ["server.py"],
  "transport": "stdio"
}
```

## Expected Output

### Console Output Example

```
🚀 MCP Server Ad Hoc Capability Testing
Server: {'url': 'http://127.0.0.1:8080/mcp', 'transport': 'streamable_http'}

🧪 Starting MCP Server Capability Tests
============================================================
Testing basic connection...
  ✅ Implemented Basic Connection: Server responsive, found 6 tools

Testing tools listing...
  ✅ Implemented Tools Listing: All 6 expected tools found

Testing tool execution...
  ✅ Implemented kubectl Execute Tool: Command executed successfully: 'kubectl version --client'
  ✅ Implemented kubectl Describe Tool: Help functionality working
  ✅ Implemented helm Execute Tool: Command executed successfully: 'helm version'
  ✅ Implemented helm Describe Tool: Help functionality working
  ✅ Implemented argocd Execute Tool: Command executed successfully: 'argocd version --client'
  ✅ Implemented argocd Describe Tool: Help functionality working

Testing resources support...
  ❌ Not Implemented Resources Support: Resources not implemented on server

Testing prompts support...
  ❌ Not Implemented Prompts Support: Prompts not implemented on server

Testing server sampling capability...
  ❌ Not Implemented Server Sampling (LLM Elicitation): Feature not testable with current client

Testing logging capability...
  ❓ Unknown Logging Support: Logging capability requires execution-time testing

Testing progress reporting...
  ❓ Unknown Progress Reporting: Progress reporting requires long-running operation testing

============================================================
MCP SERVER CAPABILITY SUMMARY
============================================================

✅ IMPLEMENTED (7):
  • Basic Connection
  • Tools Listing  
  • kubectl Execute Tool
  • kubectl Describe Tool
  • helm Execute Tool
  • helm Describe Tool
  • argocd Execute Tool
  • argocd Describe Tool

❌ NOT IMPLEMENTED (3):
  • Resources Support
  • Prompts Support
  • Server Sampling (LLM Elicitation)

❓ UNKNOWN/UNTESTABLE (2):
  • Logging Support: Logging capability requires execution-time testing
  • Progress Reporting: Progress reporting requires long-running operation testing

IMPLEMENTATION STATUS: 58.3% complete
```

### Status Icons Guide

| Icon | Status | Meaning |
|------|--------|---------|
| ✅ | Implemented | Feature is working correctly |
| ⚠️ | Partially Implemented | Feature works but has issues |
| ❌ | Not Implemented | Feature is missing |
| 🔥 | Error | Feature is broken/failing |
| ❓ | Unknown | Cannot determine status |

## Extending the Tests

### Adding Custom Capability Tests

Extend the `MCPServerCapabilityTester` class to add new tests:

#### Example: Test Kubernetes Resources

```python
async def test_kubernetes_resources(self) -> CapabilityResult:
    """Test if server exposes Kubernetes cluster info as resources"""
    try:
        # Test if server provides cluster-info, contexts, etc. as resources
        if hasattr(self.client, 'read_resource'):
            cluster_info = await self.client.read_resource("k8s://cluster-info")
            return CapabilityResult(
                name="Kubernetes Resources",
                status=CapabilityStatus.IMPLEMENTED,
                details="K8s cluster resources available",
                data={"cluster_info": str(cluster_info)[:100]}
            )
        else:
            return CapabilityResult(
                name="Kubernetes Resources", 
                status=CapabilityStatus.NOT_IMPLEMENTED,
                details="Resource reading not supported by client"
            )
    except Exception as e:
        return CapabilityResult(
            name="Kubernetes Resources",
            status=CapabilityStatus.ERROR,
            details="Failed to read K8s resources",
            error=str(e)
        )
```

#### Example: Test Command Validation

```python
async def test_command_validation(self) -> CapabilityResult:
    """Test if server validates kubectl commands before execution"""
    try:
        tools = await self.client.get_tools()
        kubectl_tool = next(tool for tool in tools if tool.name == "execute_kubectl")
        
        # Try invalid command
        result = await kubectl_tool.ainvoke({"command": "kubectl invalid-command"})
        
        # If it doesn't throw an error, validation might not be implemented
        return CapabilityResult(
            name="Command Validation",
            status=CapabilityStatus.PARTIALLY_IMPLEMENTED,
            details="Server executed invalid command without validation"
        )
        
    except Exception as e:
        if "invalid" in str(e).lower() or "not found" in str(e).lower():
            return CapabilityResult(
                name="Command Validation",
                status=CapabilityStatus.IMPLEMENTED,
                details="Server properly validates commands"
            )
        else:
            return CapabilityResult(
                name="Command Validation",
                status=CapabilityStatus.ERROR,
                details="Error testing command validation",
                error=str(e)
            )
```

## Development Workflow Integration

### During Development

Use during development to see what's working:
```bash
make start-server  # Start your MCP server
python run_mcp_tests.py  # Run capability tests
```

### CI/CD Pipeline Integration

**GitHub Actions example:** `.github/workflows/test-mcp-server.yml`
```yaml
- name: Test MCP Server Capabilities
  run: |
    python server.py &
    sleep 5  # Let server start
    python run_mcp_tests.py --output ci_results.json
    # Check if critical capabilities are implemented
```

### Debugging Specific Issues

Capture full output for debugging:
```bash
python run_mcp_tests.py --server-url http://127.0.0.1:8080/mcp 2>&1 | tee debug.log
```

### Version Comparison

Compare implementations across versions:
```bash
# Test version 1.0
python run_mcp_tests.py --output v1.0-results.json

# Make changes...

# Test version 1.1  
python run_mcp_tests.py --output v1.1-results.json

# Compare JSON files to see what changed
```

## Development Checklist

Use this script to answer key questions:

### ✅ Core Functionality
- [ ] Are all my tools discoverable?
- [ ] Do all my tools execute without errors?
- [ ] Are my help/describe tools working?

### ❓ Enhanced Features
- [ ] Should I implement resources? (cluster info, configs)
- [ ] Should I implement prompts? (common kubectl patterns)  
- [ ] Should I add logging? (command execution logs)
- [ ] Should I add progress reporting? (long-running operations)
- [ ] Should I add server sampling? (ask LLM for clarification)

### 🎯 Results
The script tells you exactly what's implemented and what's missing, giving you a clear roadmap for development priorities.

## Command Line Options

```bash
python run_mcp_tests.py [OPTIONS]

Options:
  --server-url TEXT     MCP server URL (default: http://127.0.0.1:8080/mcp)
  --transport TEXT      Transport type (default: streamable_http)  
  --config FILE         JSON config file for server connection
  --output FILE         Save results to JSON file
  --help               Show this message and exit
```

## Output Files

### JSON Results Format

When using `--output`, results are saved in this format:
```json
{
  "server_config": {
    "url": "http://127.0.0.1:8080/mcp",
    "transport": "streamable_http"
  },
  "results": [
    {
      "name": "Basic Connection",
      "status": "✅ Implemented",
      "details": "Server responsive, found 6 tools",
      "data": {"tool_count": 6},
      "error": null
    }
  ],
  "summary": "IMPLEMENTATION STATUS: 58.3% complete"
}
```

This JSON format makes it easy to:
- Parse results programmatically
- Compare across test runs
- Generate custom reports
- Integrate with monitoring systems