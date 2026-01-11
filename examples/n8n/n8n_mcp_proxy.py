#!/usr/bin/env python3
"""
HTTP MCP Proxy for n8n Integration
Strips n8n/LangChain-specific fields before forwarding to real MCP server

Usage:
    python n8n_mcp_proxy.py
    
Then configure n8n to connect to: http://localhost:9000/mcp/
"""

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
import httpx
import json
import os
from typing import Any, Dict
import uvicorn

app = FastAPI(title="n8n MCP Proxy")

# Configuration (can be overridden by environment variables)
REAL_MCP_SERVER_URL = os.getenv("REAL_MCP_SERVER_URL", "http://localhost:8080/mcp/")
PROXY_PORT = int(os.getenv("PROXY_PORT", "9000"))

# Fields to strip (n8n/LangChain artifacts)
FIELDS_TO_STRIP = {
    "toolCallId",
    "tool_call_id",
    "_meta",
    "metadata"
}


def clean_arguments(args: Dict[str, Any]) -> Dict[str, Any]:
    """Remove n8n/LangChain-specific fields from tool arguments"""
    if not isinstance(args, dict):
        return args
    return {k: v for k, v in args.items() if k not in FIELDS_TO_STRIP}


def clean_json_rpc_request(data: Dict[str, Any]) -> Dict[str, Any]:
    """Clean JSON-RPC request by removing unwanted fields from tool arguments"""
    if data.get("method") == "tools/call":
        params = data.get("params", {})
        if "arguments" in params:
            params["arguments"] = clean_arguments(params["arguments"])
            print(f"[PROXY] Cleaned tool call: {params['name']}")
            print(f"[PROXY] Cleaned arguments: {params['arguments']}")
    return data


@app.post("/mcp/")
@app.post("/mcp")
async def proxy_mcp(request: Request):
    """Proxy MCP requests, cleaning n8n-specific fields"""
    
    # Get request body
    body = await request.body()
    
    try:
        # Parse JSON-RPC request
        data = json.loads(body)
        
        # Clean the request
        cleaned_data = clean_json_rpc_request(data)
        
        # Forward to real MCP server with proper headers
        async with httpx.AsyncClient(timeout=300.0) as client:
            # Copy headers from original request and add MCP-specific ones
            forward_headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            
            # Copy User-Agent if present
            if "user-agent" in request.headers:
                forward_headers["User-Agent"] = request.headers["user-agent"]
            
            response = await client.post(
                REAL_MCP_SERVER_URL,
                json=cleaned_data,
                headers=forward_headers
            )
            
            # Return response
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
            
    except json.JSONDecodeError as e:
        return Response(
            content=json.dumps({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {str(e)}"
                },
                "id": None
            }),
            status_code=400,
            media_type="application/json"
        )
    except Exception as e:
        print(f"[PROXY ERROR] {str(e)}")
        return Response(
            content=json.dumps({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                },
                "id": None
            }),
            status_code=500,
            media_type="application/json"
        )


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "proxying_to": REAL_MCP_SERVER_URL}


if __name__ == "__main__":
    print(f"🚀 Starting n8n MCP Proxy on port {PROXY_PORT}")
    print(f"📡 Proxying to: {REAL_MCP_SERVER_URL}")
    print(f"🔧 Configure n8n to connect to: http://localhost:{PROXY_PORT}/mcp/")
    print()
    
    uvicorn.run(app, host="0.0.0.0", port=PROXY_PORT)
