"""
In-Memory Session Store.

Simple in-memory session storage for single-pod deployments,
development, and testing.

Note: Sessions are lost on server restart.
"""

import asyncio
from datetime import datetime
from typing import Any

from cbx_mcp_k8s.session.base import SessionData, SessionStore


class MemorySessionStore(SessionStore):
    """
    In-memory session storage.

    Uses a simple dictionary to store sessions. Thread-safe through
    asyncio locks. Suitable for:
    - Single-pod deployments
    - Development and testing
    - Stateless operation (sessions lost on restart)
    """

    def __init__(self, ttl_seconds: int = 3600, cleanup_interval: int = 300):
        """
        Initialize in-memory session store.

        Args:
            ttl_seconds: Session time-to-live in seconds
            cleanup_interval: How often to run cleanup (seconds)
        """
        super().__init__(ttl_seconds)
        self._sessions: dict[str, SessionData] = {}
        self._lock = asyncio.Lock()
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_loop(self) -> None:
        """Background task to periodically clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                removed = await self.cleanup_expired()
                if removed > 0:
                    import sys
                    print(f"Session cleanup: removed {removed} expired sessions", file=sys.stderr)
            except asyncio.CancelledError:
                break
            except Exception as e:
                import sys
                print(f"Session cleanup error: {e}", file=sys.stderr)

    async def create(self, session_id: str, client_info: dict[str, Any]) -> SessionData:
        """Create a new session."""
        now = datetime.now()
        session = SessionData(
            session_id=session_id,
            created_at=now,
            last_accessed=now,
            client_info=client_info,
            data={},
        )

        async with self._lock:
            self._sessions[session_id] = session

        return session

    async def get(self, session_id: str) -> SessionData | None:
        """Get session if exists and not expired."""
        async with self._lock:
            session = self._sessions.get(session_id)

            if session is None:
                return None

            if session.is_expired(self.ttl_seconds):
                # Remove expired session
                del self._sessions[session_id]
                return None

            # Update last accessed time
            session.last_accessed = datetime.now()
            return session

    async def update(self, session_id: str, data: dict[str, Any]) -> bool:
        """Update session data."""
        async with self._lock:
            session = self._sessions.get(session_id)

            if session is None:
                return False

            if session.is_expired(self.ttl_seconds):
                del self._sessions[session_id]
                return False

            # Merge data
            session.data.update(data)
            session.last_accessed = datetime.now()
            return True

    async def delete(self, session_id: str) -> bool:
        """Delete a session."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    async def touch(self, session_id: str) -> bool:
        """Update session last_accessed time."""
        async with self._lock:
            session = self._sessions.get(session_id)

            if session is None:
                return False

            if session.is_expired(self.ttl_seconds):
                del self._sessions[session_id]
                return False

            session.last_accessed = datetime.now()
            return True

    async def cleanup_expired(self) -> int:
        """Remove all expired sessions."""
        async with self._lock:
            expired = [
                sid
                for sid, session in self._sessions.items()
                if session.is_expired(self.ttl_seconds)
            ]

            for sid in expired:
                del self._sessions[sid]

            return len(expired)

    async def count(self) -> int:
        """Get number of active sessions."""
        async with self._lock:
            # Count only non-expired sessions
            return sum(
                1
                for session in self._sessions.values()
                if not session.is_expired(self.ttl_seconds)
            )

    async def get_all_sessions(self) -> list[SessionData]:
        """
        Get all active sessions (for debugging/metrics).

        Returns:
            List of active SessionData objects
        """
        async with self._lock:
            return [
                session
                for session in self._sessions.values()
                if not session.is_expired(self.ttl_seconds)
            ]
