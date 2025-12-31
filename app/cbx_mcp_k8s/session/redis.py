"""
Redis Session Store.

Redis-backed session storage for multi-pod deployments.
Provides session persistence across pod restarts and
horizontal scaling.

Note: Requires redis package: pip install redis
"""

import json
from datetime import datetime
from typing import Any

from cbx_mcp_k8s.session.base import SessionData, SessionStore


class RedisSessionStore(SessionStore):
    """
    Redis-backed session storage.

    Suitable for:
    - Multi-pod Kubernetes deployments
    - Session persistence across restarts
    - Horizontal scaling

    Session data is stored as JSON with automatic TTL expiration.
    """

    def __init__(
        self,
        redis_url: str,
        ttl_seconds: int = 3600,
        key_prefix: str = "mcp:session:",
    ):
        """
        Initialize Redis session store.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
            ttl_seconds: Session time-to-live in seconds
            key_prefix: Prefix for Redis keys
        """
        super().__init__(ttl_seconds)
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self._client = None

    async def start(self) -> None:
        """Connect to Redis on startup."""
        await self.connect()

    async def stop(self) -> None:
        """Disconnect from Redis on shutdown."""
        await self.disconnect()

    async def connect(self) -> None:
        """
        Connect to Redis.

        Raises:
            ImportError: If redis package is not installed
            ConnectionError: If cannot connect to Redis
        """
        try:
            import redis.asyncio as redis
        except ImportError:
            raise ImportError(
                "Redis session store requires the 'redis' package. "
                "Install with: pip install redis"
            )

        self._client = redis.from_url(self.redis_url)
        # Test connection
        await self._client.ping()

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _key(self, session_id: str) -> str:
        """Generate Redis key for session."""
        return f"{self.key_prefix}{session_id}"

    def _serialize(self, session: SessionData) -> str:
        """Serialize SessionData to JSON string."""
        return json.dumps({
            "session_id": session.session_id,
            "created_at": session.created_at.isoformat(),
            "last_accessed": session.last_accessed.isoformat(),
            "client_info": session.client_info,
            "data": session.data,
        })

    def _deserialize(self, data: str) -> SessionData:
        """Deserialize JSON string to SessionData."""
        obj = json.loads(data)
        return SessionData(
            session_id=obj["session_id"],
            created_at=datetime.fromisoformat(obj["created_at"]),
            last_accessed=datetime.fromisoformat(obj["last_accessed"]),
            client_info=obj.get("client_info", {}),
            data=obj.get("data", {}),
        )

    async def create(self, session_id: str, client_info: dict[str, Any]) -> SessionData:
        """Create a new session in Redis."""
        now = datetime.now()
        session = SessionData(
            session_id=session_id,
            created_at=now,
            last_accessed=now,
            client_info=client_info,
            data={},
        )

        key = self._key(session_id)
        await self._client.setex(
            key,
            self.ttl_seconds,
            self._serialize(session),
        )

        return session

    async def get(self, session_id: str) -> SessionData | None:
        """Get session from Redis and extend TTL."""
        key = self._key(session_id)
        data = await self._client.get(key)

        if data is None:
            return None

        session = self._deserialize(data)

        # Update last_accessed and refresh TTL
        session.last_accessed = datetime.now()
        await self._client.setex(
            key,
            self.ttl_seconds,
            self._serialize(session),
        )

        return session

    async def update(self, session_id: str, data: dict[str, Any]) -> bool:
        """Update session data in Redis."""
        key = self._key(session_id)
        existing = await self._client.get(key)

        if existing is None:
            return False

        session = self._deserialize(existing)
        session.data.update(data)
        session.last_accessed = datetime.now()

        await self._client.setex(
            key,
            self.ttl_seconds,
            self._serialize(session),
        )

        return True

    async def delete(self, session_id: str) -> bool:
        """Delete session from Redis."""
        key = self._key(session_id)
        result = await self._client.delete(key)
        return result > 0

    async def touch(self, session_id: str) -> bool:
        """Extend session TTL in Redis."""
        key = self._key(session_id)
        existing = await self._client.get(key)

        if existing is None:
            return False

        session = self._deserialize(existing)
        session.last_accessed = datetime.now()

        await self._client.setex(
            key,
            self.ttl_seconds,
            self._serialize(session),
        )

        return True

    async def cleanup_expired(self) -> int:
        """Redis handles TTL automatically, no cleanup needed."""
        return 0

    async def count(self) -> int:
        """Count sessions in Redis using key pattern scan."""
        pattern = f"{self.key_prefix}*"
        count = 0
        async for _ in self._client.scan_iter(match=pattern):
            count += 1
        return count


class StickySessionStore(SessionStore):
    """
    No-op session store for sticky session deployments.

    When using Kubernetes Ingress with sticky sessions,
    the ingress controller handles session affinity.
    The server only needs to maintain local state.

    This store delegates to MemorySessionStore but can
    be used to signal "sticky" deployment mode.
    """

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize sticky session store."""
        super().__init__(ttl_seconds)
        # Use memory store internally
        from cbx_mcp_k8s.session.memory import MemorySessionStore
        self._memory_store = MemorySessionStore(ttl_seconds)

    async def start(self) -> None:
        """Start the underlying memory store."""
        await self._memory_store.start()

    async def stop(self) -> None:
        """Stop the underlying memory store."""
        await self._memory_store.stop()

    async def create(self, session_id: str, client_info: dict[str, Any]) -> SessionData:
        return await self._memory_store.create(session_id, client_info)

    async def get(self, session_id: str) -> SessionData | None:
        return await self._memory_store.get(session_id)

    async def update(self, session_id: str, data: dict[str, Any]) -> bool:
        return await self._memory_store.update(session_id, data)

    async def delete(self, session_id: str) -> bool:
        return await self._memory_store.delete(session_id)

    async def touch(self, session_id: str) -> bool:
        return await self._memory_store.touch(session_id)

    async def cleanup_expired(self) -> int:
        return await self._memory_store.cleanup_expired()

    async def count(self) -> int:
        return await self._memory_store.count()
