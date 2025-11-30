# config/configuration.py

import os
import subprocess
import yaml
import json
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

from ..utils import get_logger

#############
logger = get_logger(__name__)

def load_configs(config_dir: str | None) -> tuple[dict, dict, dict, str]:
    """Load configuration with defaults from YAML and user overrides."""

    ######## MCP_CONFIG ########
    mcp_config = get_mcp_config(config_dir)

    ######## TOOLS_CONFIG ########
    # get supported tools and check which ones are installed
    tools_config = get_tools_config()

    ######## SECURITY_CONFIG ########
    security_config = get_security_config(mcp_config)

    ######## INSTRUCTIONS ########
    instructions = get_instructions()

    return mcp_config, tools_config, security_config, instructions

def get_mcp_config(config_dir: str | None):

    # 1. Load default settings
    default_settings_path = os.path.join(get_data_dir(), 'default_settings.yaml')
    try:
        with open(default_settings_path, "r") as f:
            default_config = yaml.safe_load(f) or {}
        logger.info(f"Loaded default settings from {default_settings_path}")
    except FileNotFoundError:
        raise RuntimeError(f"Default settings file not found: {default_settings_path}")
    except yaml.YAMLError as e:
        raise RuntimeError(f"Failed to parse default settings YAML '{default_settings_path}': {e}") from e

    # 2. Load user config (if exists)
    user_config = {}
    if config_dir is not None:  # config_dir will be None if both ENV var and Argument are absent
        if os.path.isdir(config_dir):
            config_path = os.path.join(config_dir, 'config.yaml')
            try:
                with open(config_path, "r") as f:
                    user_config = yaml.safe_load(f) or {}
                logger.info(f"Loaded user config from {config_path}")
            except FileNotFoundError:
                logger.info(f"User config file ({config_path}) not found. Using only default settings")
            except yaml.YAMLError as e:
                raise RuntimeError(f"Failed to parse user config YAML '{config_path}': {e}") from e
        else:
            logger.info("Config directory not found. Using only default settings")

    # 3. Deep merge: defaults + user overrides
    mcp_config = deep_merge_dicts(default_config, user_config)

    # 4. Apply environment variable overrides (highest priority)
    mcp_config = apply_env_overrides(mcp_config)

    logger.info("MCP_CONFIG loaded successfully")
    logger.debug(f"Final config: {mcp_config}")

    return mcp_config

def get_tools_config():

    # Load static tool definitions
    tools_def = get_supported_cli_tools()

    # Filter to only installed tools
    installed_tools = {}
    for tool_name, tool_config in tools_def.items():  # ✅ Iterate over key-value pairs
        if check_tool_installed(tool_config['check_cmd']):  # ✅ Use tool_config, not tool
            installed_tools[tool_name] = tool_config  # ✅ Use tool_name as key

    return installed_tools

def get_instructions():
    context = get_supported_cli_tools()

    # Point Jinja2 to the correct directory
    data_dir = get_data_dir()
    jinja_env = Environment(loader=FileSystemLoader(data_dir))  #  dir with templates

    # Use just the filename, not full path
    template = jinja_env.get_template("instructions.j2")  # template filename

    # render instructions for all supported tools
    instructions = template.render(context=context)
    return instructions

######## utils

def deep_merge_dicts(default_dict: dict, override_dict: dict) -> dict:
    """Deep merge two dictionaries, with override_dict taking precedence."""
    result = default_dict.copy()

    for key, value in override_dict.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value

    return result

def get_data_dir():
    # 1. Get path to data directory assuming this file is already in "config" module dir
    current_dir = Path(__file__).parent  # This is the "config" directory
    data_dir = os.path.join(current_dir,"data")
    return data_dir

def get_supported_cli_tools():
    tools_list_path = os.path.join(get_data_dir(), "supported_cli_tools.json")

    with open(tools_list_path, 'r') as file:
        supported_cli_tools = json.load(file)

    return supported_cli_tools

def check_tool_installed(install_check_command: str) -> bool:
    """Simple subprocess call to verify tool installation"""
    try:
        result = subprocess.run(
            install_check_command.split(),
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False



def get_security_config(mcp_config: dict) -> dict:
    """Load security configuration from YAML file or use defaults."""

    # Load default settings from file
    default_config_path = os.path.join(get_data_dir(), 'default_security_config.yaml')
    with open(default_config_path, "r") as f:
        default_security_config = yaml.safe_load(f)

    # Initialize from defaults - these MUST exist in the default config
    dangerous_commands = default_security_config.get("dangerous_commands", {}).copy()
    safe_patterns = default_security_config.get("safe_patterns", {}).copy()
    allowed_unix_commands = default_security_config.get("allowed_unix_commands", []).copy()

    # Load regex rules from defaults
    regex_rules = {}
    for tool, rules in default_security_config.get("regex_rules", {}).items():
        regex_rules[tool] = []
        for rule in rules:
            regex_rules[tool].append({
                "pattern": rule["pattern"],
                "description": rule.get("description", ""),
                "error_message": rule.get("error_message",
                                          f"Command matches restricted pattern: {rule['pattern']}"),
                "regex": True,
            })

    # Override with custom config if provided
    security_config_path = mcp_config.get('security', {}).get("security_config_path")
    if security_config_path and Path(security_config_path).exists():
        with open(security_config_path) as f:
            config_data = yaml.safe_load(f) or {}

        # Update with custom settings
        dangerous_commands.update(config_data.get("dangerous_commands", {}))
        safe_patterns.update(config_data.get("safe_patterns", {}))

        # Update allowed unix commands (replace if provided)
        if "allowed_unix_commands" in config_data:
            allowed_unix_commands = config_data["allowed_unix_commands"]

        # Load additional regex rules from custom config
        for tool, rules in config_data.get("regex_rules", {}).items():
            if tool not in regex_rules:
                regex_rules[tool] = []
            for rule in rules:
                regex_rules[tool].append({
                    "pattern": rule["pattern"],
                    "description": rule.get("description", ""),
                    "error_message": rule.get("error_message",
                                              f"Command matches restricted pattern: {rule['pattern']}"),
                    "regex": True,
                })

    return {
        'dangerous_commands': dangerous_commands,
        'safe_patterns': safe_patterns,
        'regex_rules': regex_rules,
        'allowed_unix_commands': allowed_unix_commands,
    }


def apply_env_overrides(config_dict: dict) -> dict:

    # Get all CBX_MCP_ environment variables
    cbx_env_vars = {k: v for k, v in os.environ.items() if k.startswith('CBX_MCP_')}

    if not cbx_env_vars:
        logger.debug("No CBX_MCP_ env overrides found. Skipping.")
        return config_dict

    logger.info(f"Processing {len(cbx_env_vars)} environment variable overrides")

    for env_key, env_value in cbx_env_vars.items():
        try:
            # Parse CBX_MCP_<SECTION>_<KEY>
            section, key = parse_env_key(env_key)
            # Convert to proper type (as in YAML)
            typed_value = yaml.safe_load(env_value)

            set_nested_value(config_dict, section, key, typed_value)

            logger.info(f"ENV override: {section}.{key}={typed_value} (from {env_key})")

        except ValueError as e:
            logger.error(f"Invalid env variable format '{env_key}': {e}. Skipping.")
            continue
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML value in '{env_key}={env_value}': {e}. Skipping.")
            continue
        except Exception as e:
            logger.error(f"Error processing env override '{env_key}={env_value}': {e}. Skipping.")
            continue

    return config_dict


def parse_env_key(env_key: str) -> tuple[str, str]:

    # Remove CBX_MCP_ prefix
    remainder = env_key[8:]  # len('CBX_MCP_') = 8

    if not remainder:
        raise ValueError("Environment variable must have content after 'CBX_MCP_'")

    # Split on first underscore to get section and key
    parts = remainder.split('_', 1)

    if len(parts) != 2:
        raise ValueError(f"Environment variable must follow pattern 'CBX_MCP_<SECTION>_<KEY>'")

    section, key = parts

    if not section or not key:
        raise ValueError("Both section and key must be non-empty")

    # Convert to lowercase
    return section.lower(), key.lower()


def set_nested_value(config_dict: dict, section: str, key: str, value) -> None:

    # Ensure section exists
    if section not in config_dict:
        config_dict[section] = {}

    # Set the value
    config_dict[section][key] = value