"""
Configuration loader with YAML and environment variable support.

Priority (highest to lowest):
1. Environment variables: CBX_MCP_SERVER__PORT=9000
2. User config: --config-dir path / ~/.k8smcp/config.yaml
3. Built-in defaults: cbx_mcp_k8s/config/defaults/
"""

import os
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

from cbx_mcp_k8s.config.models import K8sMCPServerConfig


# Default config locations
DEFAULT_CONFIG_DIR = Path.home() / ".k8smcp"
PACKAGE_DEFAULTS_DIR = Path(__file__).parent / "defaults"

# Environment variable prefix
ENV_PREFIX = "CBX_MCP_"
ENV_DELIMITER = "__"


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge two dictionaries.

    Values from 'override' take precedence over 'base'.
    Nested dicts are merged recursively.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning empty dict if not found."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            content = yaml.safe_load(f)
            return content if content else {}
    except yaml.YAMLError as e:
        print(f"Warning: Failed to parse {path}: {e}", file=sys.stderr)
        return {}


def _get_env_overrides() -> dict[str, Any]:
    """
    Extract configuration overrides from environment variables.

    Environment variables are expected in the format:
    CBX_MCP_SECTION__KEY=value

    For nested keys, use double underscore as delimiter:
    CBX_MCP_SERVER__PORT=9000 -> {"server": {"port": 9000}}
    CBX_MCP_SESSION__PERSISTENCE=redis -> {"session": {"persistence": "redis"}}
    """
    overrides: dict[str, Any] = {}

    for key, value in os.environ.items():
        if not key.startswith(ENV_PREFIX):
            continue

        # Remove prefix and split by delimiter
        key_path = key[len(ENV_PREFIX) :].lower().split(ENV_DELIMITER)

        # Build nested dict
        current = overrides
        for part in key_path[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        # Convert value to appropriate type
        final_key = key_path[-1]
        current[final_key] = _parse_env_value(value)

    return overrides


def _parse_env_value(value: str) -> Any:
    """Parse environment variable value to appropriate Python type."""
    # Boolean
    if value.lower() in ("true", "yes", "1"):
        return True
    if value.lower() in ("false", "no", "0"):
        return False

    # Integer
    try:
        return int(value)
    except ValueError:
        pass

    # Float
    try:
        return float(value)
    except ValueError:
        pass

    # String (default)
    return value


def load_config(config_dir: Optional[str | Path] = None) -> K8sMCPServerConfig:
    """
    Load configuration from multiple sources.

    Args:
        config_dir: Optional path to configuration directory.
                   If not provided, uses ~/.k8smcp/

    Returns:
        K8sMCPServerConfig: Validated configuration object

    Raises:
        ValueError: If configuration is invalid
    """
    # Start with package defaults
    config_data = _load_yaml_file(PACKAGE_DEFAULTS_DIR / "settings.yaml")

    # Merge security config
    security_data = _load_yaml_file(PACKAGE_DEFAULTS_DIR / "security.yaml")
    config_data = _deep_merge(config_data, security_data)

    # Merge user config
    user_config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    user_config = _load_yaml_file(user_config_dir / "config.yaml")
    config_data = _deep_merge(config_data, user_config)

    # Merge security overrides from user config
    user_security = _load_yaml_file(user_config_dir / "security.yaml")
    config_data = _deep_merge(config_data, user_security)

    # Apply environment variable overrides (highest priority)
    env_overrides = _get_env_overrides()
    config_data = _deep_merge(config_data, env_overrides)

    # Validate and return
    return K8sMCPServerConfig.model_validate(config_data)


def reload_config(
    current_config: K8sMCPServerConfig, config_dir: Optional[str | Path] = None
) -> K8sMCPServerConfig:
    """
    Reload configuration (for SIGHUP handling).

    Args:
        current_config: Current configuration (for fallback on error)
        config_dir: Configuration directory path

    Returns:
        K8sMCPServerConfig: New configuration, or current if reload fails
    """
    try:
        return load_config(config_dir)
    except Exception as e:
        print(f"Warning: Config reload failed, keeping current config: {e}", file=sys.stderr)
        return current_config
