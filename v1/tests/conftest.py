# tests/conftest.py
"""
Shared pytest fixtures for CBX MCP Server tests.
"""

import pytest
import os
import sys

# Add app to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(scope="session", autouse=True)
def initialize_config():
    """Initialize configuration before any tests run."""
    from app.cbx_mcp_k8s.config import ConfigManager
    ConfigManager.initialize()
    yield


@pytest.fixture
def strict_security_mode(monkeypatch):
    """Set security mode to strict for testing."""
    from app.cbx_mcp_k8s import config
    original_mode = config.MCP_CONFIG.get('security', {}).get('security_mode')
    config.MCP_CONFIG['security']['security_mode'] = 'strict'
    yield
    config.MCP_CONFIG['security']['security_mode'] = original_mode


@pytest.fixture
def permissive_security_mode(monkeypatch):
    """Set security mode to permissive for testing."""
    from app.cbx_mcp_k8s import config
    original_mode = config.MCP_CONFIG.get('security', {}).get('security_mode')
    config.MCP_CONFIG['security']['security_mode'] = 'permissive'
    yield
    config.MCP_CONFIG['security']['security_mode'] = original_mode


@pytest.fixture
def security_config():
    """Get the security configuration."""
    from app.cbx_mcp_k8s.config import SECURITY_CONFIG
    return SECURITY_CONFIG


@pytest.fixture
def tools_config():
    """Get the tools configuration."""
    from app.cbx_mcp_k8s.config import TOOLS_CONFIG
    return TOOLS_CONFIG


@pytest.fixture
def mcp_config():
    """Get the MCP configuration."""
    from app.cbx_mcp_k8s.config import MCP_CONFIG
    return MCP_CONFIG