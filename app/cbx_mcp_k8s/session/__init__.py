"""
Session Management for MCP Server.

Provides session storage backends for maintaining state
between MCP requests. Supports multiple persistence modes:

- memory: In-memory storage (single pod, dev/testing)
- redis: Redis-backed (multi-pod, production)
- sticky: Ingress sticky sessions (K8s specific)

Also provides EventStore implementations for MCP protocol
session resumability (separate from application session data).
"""

from cbx_mcp_k8s.session.base import SessionData, SessionStore
from cbx_mcp_k8s.session.event_store import InMemoryEventStore, RedisEventStore
from cbx_mcp_k8s.session.memory import MemorySessionStore
from cbx_mcp_k8s.session.redis import RedisSessionStore, StickySessionStore

__all__ = [
    # Application session data
    "SessionData",
    "SessionStore",
    "MemorySessionStore",
    "RedisSessionStore",
    "StickySessionStore",
    "create_session_store",
    # MCP protocol event store (for resumability)
    "RedisEventStore",
    "InMemoryEventStore",
    "create_event_store",
]


def create_session_store(
    persistence: str,
    ttl_seconds: int = 3600,
    redis_url: str | None = None,
) -> SessionStore:
    """
    Factory function to create appropriate session store.

    Args:
        persistence: Storage type - "memory", "redis", or "sticky"
        ttl_seconds: Session time-to-live in seconds
        redis_url: Redis URL (required for "redis" persistence)

    Returns:
        Configured SessionStore instance

    Raises:
        ValueError: If invalid persistence type or missing redis_url
    """
    if persistence == "memory":
        return MemorySessionStore(ttl_seconds=ttl_seconds)

    elif persistence == "redis":
        if not redis_url:
            raise ValueError("redis_url is required for redis persistence")
        return RedisSessionStore(redis_url=redis_url, ttl_seconds=ttl_seconds)

    elif persistence == "sticky":
        return StickySessionStore(ttl_seconds=ttl_seconds)

    else:
        raise ValueError(
            f"Invalid persistence type: {persistence}. "
            f"Must be one of: memory, redis, sticky"
        )


def create_event_store(
    persistence: str,
    redis_url: str | None = None,
    max_events: int = 1000,
    ttl_seconds: int = 3600,
) -> RedisEventStore | InMemoryEventStore | None:
    """
    Factory function to create appropriate event store for MCP resumability.

    The event store enables session resumability - clients can reconnect
    and replay missed events after disconnection or pod restart.

    Args:
        persistence: Storage type - "memory", "redis", or "none"
        redis_url: Redis URL (required for "redis" persistence)
        max_events: Maximum events to keep per stream
        ttl_seconds: Event TTL in seconds

    Returns:
        Configured EventStore instance, or None if disabled

    Raises:
        ValueError: If invalid persistence type or missing redis_url
    """
    if persistence == "none" or persistence is None:
        return None

    elif persistence == "memory":
        return InMemoryEventStore(max_events_per_stream=max_events)

    elif persistence == "redis":
        if not redis_url:
            raise ValueError("redis_url is required for redis event store")
        return RedisEventStore(
            redis_url=redis_url,
            max_events_per_stream=max_events,
            ttl_seconds=ttl_seconds,
        )

    else:
        raise ValueError(
            f"Invalid event store type: {persistence}. "
            f"Must be one of: none, memory, redis"
        )
