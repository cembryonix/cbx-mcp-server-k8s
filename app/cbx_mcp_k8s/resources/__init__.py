# resources/__init__.py

def register_resources(mcp,config):

    register_resources_kubectl(mcp, config)

def register_resources_kubectl(mcp, config):

    # Register resources
    @mcp.resource("kubectl://clusters")
    async def list_clusters() -> str:
        """List available clusters from kubeconfig"""
        pass

    @mcp.resource("kubectl://clusters/{cluster}/namespaces")
    async def list_namespaces(cluster: str) -> str:
        """List namespaces for specific cluster"""
        pass