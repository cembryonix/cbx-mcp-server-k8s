# config/__init__.py

# Global configuration variables - these get updated by the manager
MCP_CONFIG = {}
TOOLS_CONFIG = {}
SECURITY_CONFIG = {
    'dangerous_commands': {},
    'safe_patterns': {},
    'regex_rules': {}
}
INSTRUCTIONS = ""
from .configuration import load_configs

from ..utils import get_logger
logger = get_logger(__name__)

class ConfigManager:
    """Manages global configuration state with refresh capability."""

    _initialized = False

    @classmethod
    def initialize(cls, config_dir: str | None = None):
        """Initialize or refresh all global configuration variables."""
        global MCP_CONFIG, TOOLS_CONFIG, SECURITY_CONFIG, INSTRUCTIONS

        # Load fresh configuration
        mcp_config, tools_config, security_config, instructions = load_configs(config_dir)

        # Update global variables
        MCP_CONFIG.clear()
        MCP_CONFIG.update(mcp_config)

        TOOLS_CONFIG.clear()
        TOOLS_CONFIG.update(tools_config)

        # Update SECURITY_CONFIG nested dicts
        SECURITY_CONFIG['dangerous_commands'].clear()
        SECURITY_CONFIG['dangerous_commands'].update(security_config.get('dangerous_commands', {}))

        SECURITY_CONFIG['safe_patterns'].clear()
        SECURITY_CONFIG['safe_patterns'].update(security_config.get('safe_patterns', {}))

        SECURITY_CONFIG['regex_rules'].clear()
        SECURITY_CONFIG['regex_rules'].update(security_config.get('regex_rules', {}))

        INSTRUCTIONS = instructions

        cls._initialized = True

        # Debug logging
        logger.info(f"Configuration refreshed. Security mode: {MCP_CONFIG.get('security', {}).get('security_mode')}")

    @classmethod
    def ensure_initialized(cls):
        """Ensure configuration is initialized with defaults if not already done."""
        if not cls._initialized:
            cls.initialize()


# Initialize with defaults on module import
ConfigManager.ensure_initialized()


def reinitialize_configs(config_dir: str | None = None):
    """Refresh all global configuration variables."""
    ConfigManager.initialize(config_dir)




__all__ = ['MCP_CONFIG', 'TOOLS_CONFIG', 'SECURITY_CONFIG', 'INSTRUCTIONS', 'reinitialize_configs']

