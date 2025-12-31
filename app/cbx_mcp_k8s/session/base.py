"""
Session Store Base Interface.

Defines the abstract interface for session storage backends.
Sessions are used to maintain state between MCP requests.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SessionData:
    """
    Data stored for each session.

    Attributes:
        session_id: Unique session identifier
        created_at: When session was created
        last_accessed: When session was last accessed
        client_info: Client information from MCP initialize
        data: Arbitrary session data
    """

    session_id: str
    created_at: datetime
    last_accessed: datetime
    client_info: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if session has expired based on TTL."""
        age = (datetime.now() - self.last_accessed).total_seconds()
        return age > ttl_seconds


class SessionStore(ABC):
    """
    Abstract interface for session storage backends.

    Implementations:
    - MemorySessionStore: In-memory storage (single pod, dev/testing)
    - RedisSessionStore: Redis-backed (multi-pod, production)
    - StickySessionStore: No-op (ingress handles sessions)
    """

    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize session store.

        Args:
            ttl_seconds: Session time-to-live in seconds
        """
        self.ttl_seconds = ttl_seconds

    @abstractmethod
    async def create(self, session_id: str, client_info: dict[str, Any]) -> SessionData:
        """
        Create a new session.

        Args:
            session_id: Unique session identifier
            client_info: Client information from MCP initialize

        Returns:
            Created SessionData
        """
        pass

    @abstractmethod
    async def get(self, session_id: str) -> SessionData | None:
        """
        Retrieve session data.

        Args:
            session_id: Session identifier

        Returns:
            SessionData if found and not expired, None otherwise
        """
        pass

    @abstractmethod
    async def update(self, session_id: str, data: dict[str, Any]) -> bool:
        """
        Update session data.

        Args:
            session_id: Session identifier
            data: Data to merge into session

        Returns:
            True if session was updated, False if not found
        """
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: Session identifier

        Returns:
            True if session was deleted, False if not found
        """
        pass

    @abstractmethod
    async def touch(self, session_id: str) -> bool:
        """
        Update session last_accessed time (extend TTL).

        Args:
            session_id: Session identifier

        Returns:
            True if session was touched, False if not found
        """
        pass

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """
        Remove expired sessions.

        Returns:
            Number of sessions removed
        """
        pass

    @abstractmethod
    async def count(self) -> int:
        """
        Get number of active sessions.

        Returns:
            Number of active (non-expired) sessions
        """
        pass
