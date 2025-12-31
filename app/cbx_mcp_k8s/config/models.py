"""
Pydantic models for server configuration.

This replaces the global config pattern from v1 with explicit,
type-safe configuration classes.
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SessionPersistence(str, Enum):
    """Session storage backend options."""

    MEMORY = "memory"  # In-memory, single pod (stateless from K8s perspective)
    REDIS = "redis"  # Redis-backed, multi-pod support
    STICKY = "sticky"  # Relies on K8s ingress sticky sessions


class EventStorePersistence(str, Enum):
    """Event store backend options for MCP session resumability."""

    NONE = "none"  # Disabled - no resumability support
    MEMORY = "memory"  # In-memory (single pod, dev/testing)
    REDIS = "redis"  # Redis Streams (multi-pod, production)


class ServerSettings(BaseModel):
    """Server configuration settings."""

    host: str = Field(
        default="127.0.0.1",
        description="Host to bind the server to",
    )
    port: int = Field(
        default=8080,
        ge=1,
        le=65535,
        description="Port to listen on",
    )
    transport: Literal["streamable-http", "stdio"] = Field(
        default="streamable-http",
        description="Transport protocol to use",
    )
    log_level: Literal["debug", "info", "warning", "error"] = Field(
        default="info",
        description="Logging level",
    )


class SessionSettings(BaseModel):
    """Session management configuration."""

    persistence: SessionPersistence = Field(
        default=SessionPersistence.MEMORY,
        description="Session storage backend",
    )
    ttl_seconds: int = Field(
        default=3600,
        ge=60,
        description="Session timeout in seconds",
    )
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis connection URL (required if persistence=redis)",
    )

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: Optional[str], info) -> Optional[str]:
        """Ensure redis_url is set when persistence is redis."""
        # Note: Cross-field validation happens in K8sMCPServerConfig.model_validate
        return v


class EventStoreSettings(BaseModel):
    """
    Event store configuration for MCP protocol resumability.

    The event store enables session resumability - clients can reconnect
    after disconnection (network issues, pod restart) and replay missed
    events. This is separate from SessionSettings which stores application data.

    For production K8s deployments, use "redis" to enable:
    - Pod restart resilience
    - Horizontal scaling (any pod can serve any session)
    - Client reconnection with event replay
    """

    persistence: EventStorePersistence = Field(
        default=EventStorePersistence.NONE,
        description="Event store backend (none, memory, redis)",
    )
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis connection URL (required if persistence=redis)",
    )
    max_events: int = Field(
        default=1000,
        ge=10,
        le=10000,
        description="Maximum events to keep per session stream",
    )
    ttl_seconds: int = Field(
        default=3600,
        ge=60,
        description="Event TTL in seconds",
    )


class CommandSettings(BaseModel):
    """Command execution settings."""

    default_timeout: int = Field(
        default=60,
        ge=1,
        le=600,
        description="Default command timeout in seconds",
    )
    max_output_size: int = Field(
        default=100000,
        ge=1000,
        description="Maximum output size in bytes before truncation",
    )


class SecuritySettings(BaseModel):
    """Security configuration."""

    mode: Literal["strict", "permissive"] = Field(
        default="strict",  # Changed from v1's "permissive" default
        description="Security validation mode",
    )

    # Command validation rules
    dangerous_commands: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Commands blocked by default, keyed by tool name",
    )
    safe_patterns: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Exceptions to dangerous commands, keyed by tool name",
    )
    regex_rules: dict[str, list[dict]] = Field(
        default_factory=dict,
        description="Regex-based validation rules, keyed by tool name",
    )
    allowed_unix_commands: list[str] = Field(
        default_factory=list,
        description="Unix commands allowed in pipe chains",
    )


class K8sMCPServerConfig(BaseModel):
    """
    Main configuration container for CBX MCP K8s Server.

    This class replaces the global config pattern from v1.
    Configuration is loaded from YAML files and environment variables,
    then passed to server components via dependency injection.
    """

    server: ServerSettings = Field(default_factory=ServerSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)
    event_store: EventStoreSettings = Field(default_factory=EventStoreSettings)
    command: CommandSettings = Field(default_factory=CommandSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

    @field_validator("session")
    @classmethod
    def validate_session_redis(cls, v: SessionSettings) -> SessionSettings:
        """Ensure redis_url is set when using Redis persistence."""
        if v.persistence == SessionPersistence.REDIS and not v.redis_url:
            raise ValueError(
                "redis_url is required when session.persistence is 'redis'"
            )
        return v

    @field_validator("event_store")
    @classmethod
    def validate_event_store_redis(cls, v: EventStoreSettings) -> EventStoreSettings:
        """Ensure redis_url is set when using Redis event store."""
        if v.persistence == EventStorePersistence.REDIS and not v.redis_url:
            raise ValueError(
                "redis_url is required when event_store.persistence is 'redis'"
            )
        return v

    # Allow extra fields to be ignored (forward compatibility)
    model_config = ConfigDict(extra="ignore")
