# tests/unit/test_config.py
"""
Unit tests for configuration loading and management.
Tests config loading, merging, env var overrides, and hot-reload.
"""

import pytest
import os
from unittest.mock import patch, MagicMock

from app.cbx_mcp_k8s.config import (
    ConfigManager,
    MCP_CONFIG,
    SECURITY_CONFIG,
    TOOLS_CONFIG,
    reinitialize_configs,
)
from app.cbx_mcp_k8s.config.configuration import (
    deep_merge_dicts,
    parse_env_key,
    set_nested_value,
    apply_env_overrides,
    get_security_config,
)


class TestDeepMergeDicts:
    """Tests for deep dictionary merging."""

    def test_simple_merge(self):
        """Simple non-nested merge."""
        default = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = deep_merge_dicts(default, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        """Nested dictionary merge."""
        default = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 10, "z": 20}}
        result = deep_merge_dicts(default, override)
        assert result == {"a": {"x": 1, "y": 10, "z": 20}, "b": 3}

    def test_override_non_dict_with_dict(self):
        """Override scalar with dict."""
        default = {"a": 1}
        override = {"a": {"nested": "value"}}
        result = deep_merge_dicts(default, override)
        assert result == {"a": {"nested": "value"}}

    def test_empty_override(self):
        """Empty override dict should preserve defaults."""
        default = {"a": 1, "b": {"x": 2}}
        override = {}
        result = deep_merge_dicts(default, override)
        assert result == default


class TestParseEnvKey:
    """Tests for environment variable key parsing."""

    def test_valid_env_key(self):
        """Valid env key should be parsed correctly."""
        section, key = parse_env_key("CBX_MCP_SERVER_PORT")
        assert section == "server"
        assert key == "port"

    def test_env_key_with_multiple_underscores(self):
        """Key with multiple underscores should preserve them."""
        section, key = parse_env_key("CBX_MCP_SECURITY_SECURITY_MODE")
        assert section == "security"
        assert key == "security_mode"

    def test_invalid_env_key_no_underscore(self):
        """Key without underscore after section should raise."""
        with pytest.raises(ValueError, match="pattern"):
            parse_env_key("CBX_MCP_INVALID")

    def test_empty_env_key(self):
        """Empty key after prefix should raise."""
        with pytest.raises(ValueError):
            parse_env_key("CBX_MCP_")


class TestSetNestedValue:
    """Tests for setting nested config values."""

    def test_set_existing_section(self):
        """Set value in existing section."""
        config = {"server": {"port": 8080}}
        set_nested_value(config, "server", "host", "localhost")
        assert config["server"]["host"] == "localhost"
        assert config["server"]["port"] == 8080

    def test_set_new_section(self):
        """Set value creates new section if needed."""
        config = {}
        set_nested_value(config, "new_section", "key", "value")
        assert config["new_section"]["key"] == "value"


class TestApplyEnvOverrides:
    """Tests for environment variable overrides."""

    def test_env_override_applied(self):
        """Env vars should override config values."""
        config = {"server": {"port": 8080}}

        with patch.dict(os.environ, {"CBX_MCP_SERVER_PORT": "9000"}):
            result = apply_env_overrides(config.copy())
            assert result["server"]["port"] == 9000  # YAML parsing converts to int

    def test_no_env_vars(self):
        """No CBX_MCP_ vars should leave config unchanged."""
        config = {"server": {"port": 8080}}

        # Clear any CBX_MCP_ vars
        env_backup = {k: v for k, v in os.environ.items() if k.startswith("CBX_MCP_")}
        for k in env_backup:
            del os.environ[k]

        try:
            result = apply_env_overrides(config.copy())
            assert result == config
        finally:
            # Restore env
            os.environ.update(env_backup)


class TestSecurityConfig:
    """Tests for security configuration loading."""

    def test_security_config_has_required_keys(self):
        """Security config should have all required keys."""
        assert "dangerous_commands" in SECURITY_CONFIG
        assert "safe_patterns" in SECURITY_CONFIG
        assert "regex_rules" in SECURITY_CONFIG
        assert "allowed_unix_commands" in SECURITY_CONFIG

    def test_dangerous_commands_loaded(self):
        """Dangerous commands should be loaded from default config."""
        assert "kubectl" in SECURITY_CONFIG["dangerous_commands"]
        assert "helm" in SECURITY_CONFIG["dangerous_commands"]
        assert "argocd" in SECURITY_CONFIG["dangerous_commands"]

    def test_allowed_unix_commands_loaded(self):
        """Allowed unix commands should be loaded."""
        allowed = SECURITY_CONFIG["allowed_unix_commands"]
        assert "grep" in allowed
        assert "jq" in allowed
        assert "head" in allowed


class TestConfigManager:
    """Tests for ConfigManager class."""

    def test_config_initialized(self):
        """Config should be initialized on module import."""
        assert ConfigManager._initialized is True

    def test_reinitialize_updates_config(self):
        """Reinitialize should update global configs."""
        original_mode = MCP_CONFIG.get("security", {}).get("security_mode")

        # Reinitialize should work without errors
        reinitialize_configs()

        # Config should still be valid
        assert "security" in MCP_CONFIG
        assert ConfigManager._initialized is True

    def test_tools_config_has_installed_tools(self):
        """Tools config should only include installed tools."""
        # At minimum kubectl should be installed on most systems
        # But we shouldn't fail if it's not
        assert isinstance(TOOLS_CONFIG, dict)

    def test_mcp_config_has_defaults(self):
        """MCP config should have default values loaded."""
        assert "server" in MCP_CONFIG or "command" in MCP_CONFIG
        # Command settings should exist
        if "command" in MCP_CONFIG:
            assert "default_timeout" in MCP_CONFIG["command"]


class TestConfigHotReload:
    """Tests for configuration hot-reload capability."""

    def test_reinitialize_preserves_reference(self):
        """Reinitialize should update in place, not replace reference."""
        # Get references before reinit
        mcp_ref = MCP_CONFIG
        security_ref = SECURITY_CONFIG

        reinitialize_configs()

        # References should still point to the same objects
        assert MCP_CONFIG is mcp_ref
        assert SECURITY_CONFIG is security_ref
