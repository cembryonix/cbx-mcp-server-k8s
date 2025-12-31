"""
Redis Event Store for MCP Session Resumability.

Implements the EventStore interface using Redis Streams for
persistent event storage. This enables:
- Session resumability after pod restarts
- Horizontal scaling with any-pod routing
- Event replay for client reconnection

Redis Streams are ideal for this use case:
- Ordered, immutable event log
- Efficient range queries (XRANGE)
- Automatic ID generation (timestamp-based)
- TTL support via XTRIM
"""

import json
import logging
from collections.abc import Awaitable, Callable

from mcp.server.streamable_http import EventMessage, EventStore
from mcp.types import JSONRPCMessage

logger = logging.getLogger(__name__)

# Type aliases matching MCP SDK
StreamId = str
EventId = str
EventCallback = Callable[[EventMessage], Awaitable[None]]


class RedisEventStore(EventStore):
    """
    Redis Streams-backed event store for MCP session resumability.

    Stores events in Redis Streams with format:
        Key: {prefix}:stream:{stream_id}
        Fields: {"message": <json>, "type": "event"}

    Event IDs use Redis Stream auto-generated IDs (timestamp-sequence).
    """

    def __init__(
        self,
        redis_url: str,
        prefix: str = "mcp:events",
        max_events_per_stream: int = 1000,
        ttl_seconds: int = 3600,
    ):
        """
        Initialize Redis event store.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
            prefix: Key prefix for Redis streams
            max_events_per_stream: Max events to keep per stream (older trimmed)
            ttl_seconds: TTL for streams (approximate, via periodic cleanup)
        """
        self.redis_url = redis_url
        self.prefix = prefix
        self.max_events = max_events_per_stream
        self.ttl_seconds = ttl_seconds
        self._client = None

    async def connect(self) -> None:
        """Connect to Redis."""
        if self._client is not None:
            return

        try:
            import redis.asyncio as redis
        except ImportError:
            raise ImportError(
                "Redis event store requires the 'redis' package. "
                "Install with: pip install redis"
            )

        self._client = redis.from_url(self.redis_url)
        await self._client.ping()
        logger.info(f"RedisEventStore connected to {self.redis_url}")

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("RedisEventStore disconnected")

    def _stream_key(self, stream_id: StreamId) -> str:
        """Generate Redis key for a stream."""
        return f"{self.prefix}:stream:{stream_id}"

    def _parse_event_id(self, event_id: EventId) -> tuple[StreamId, str]:
        """
        Parse composite event ID into stream_id and redis_id.

        Format: {stream_id}:{redis_stream_id}
        Example: "session-abc:1234567890-0"
        """
        # Event ID format: stream_id:redis_id
        # Redis stream IDs contain '-', so split from the right
        parts = event_id.rsplit(":", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid event ID format: {event_id}")
        return parts[0], parts[1]

    def _make_event_id(self, stream_id: StreamId, redis_id: str) -> EventId:
        """Create composite event ID from stream_id and redis_id."""
        return f"{stream_id}:{redis_id}"

    async def store_event(
        self,
        stream_id: StreamId,
        message: JSONRPCMessage | None,
    ) -> EventId:
        """
        Store an event in Redis Stream.

        Args:
            stream_id: ID of the stream (typically session ID)
            message: JSON-RPC message to store, or None for priming events

        Returns:
            Composite event ID (stream_id:redis_stream_id)
        """
        if self._client is None:
            await self.connect()

        key = self._stream_key(stream_id)

        # Serialize message
        if message is not None:
            # JSONRPCMessage is a Pydantic model or TypedDict
            if hasattr(message, "model_dump"):
                msg_data = json.dumps(message.model_dump())
            elif hasattr(message, "dict"):
                msg_data = json.dumps(message.dict())
            else:
                msg_data = json.dumps(message)
        else:
            msg_data = ""

        # Add to stream with auto-generated ID
        redis_id = await self._client.xadd(
            key,
            {"message": msg_data, "type": "event"},
            maxlen=self.max_events,
            approximate=True,
        )

        # Set TTL on the stream key (refreshed on each write)
        await self._client.expire(key, self.ttl_seconds)

        event_id = self._make_event_id(stream_id, redis_id)
        logger.debug(f"Stored event {event_id}")

        return event_id

    async def replay_events_after(
        self,
        last_event_id: EventId,
        send_callback: EventCallback,
    ) -> StreamId | None:
        """
        Replay events that occurred after the specified event ID.

        Args:
            last_event_id: The last event ID the client received
            send_callback: Callback to send each event to the client

        Returns:
            The stream ID if events were replayed, None otherwise
        """
        if self._client is None:
            await self.connect()

        try:
            stream_id, redis_id = self._parse_event_id(last_event_id)
        except ValueError as e:
            logger.warning(f"Invalid event ID for replay: {e}")
            return None

        key = self._stream_key(stream_id)

        # Read events after the given ID (exclusive)
        # XRANGE with "(" prefix for exclusive start
        events = await self._client.xrange(key, min=f"({redis_id}", max="+")

        if not events:
            logger.debug(f"No events to replay after {last_event_id}")
            return None

        logger.info(f"Replaying {len(events)} events for stream {stream_id}")

        for redis_event_id, fields in events:
            msg_data = fields.get(b"message") or fields.get("message")

            if msg_data:
                if isinstance(msg_data, bytes):
                    msg_data = msg_data.decode("utf-8")

                # Parse the stored message
                if msg_data:
                    try:
                        message_dict = json.loads(msg_data)
                    except json.JSONDecodeError:
                        message_dict = None
                else:
                    message_dict = None
            else:
                message_dict = None

            event_id = self._make_event_id(stream_id, redis_event_id)

            # Create EventMessage and send via callback
            event_message = EventMessage(
                event_id=event_id,
                message=message_dict,
            )
            await send_callback(event_message)

        return stream_id

    async def cleanup_old_streams(self, max_age_seconds: int | None = None) -> int:
        """
        Clean up old streams that have expired.

        This is handled automatically by Redis TTL, but can be called
        manually for more aggressive cleanup.

        Args:
            max_age_seconds: Max age for streams (uses self.ttl_seconds if None)

        Returns:
            Number of streams deleted
        """
        if self._client is None:
            await self.connect()

        # Redis TTL handles this automatically, but we can scan for
        # streams without TTL and clean them up
        pattern = f"{self.prefix}:stream:*"
        deleted = 0

        async for key in self._client.scan_iter(match=pattern):
            ttl = await self._client.ttl(key)
            if ttl == -1:  # No TTL set
                await self._client.expire(key, max_age_seconds or self.ttl_seconds)
                deleted += 1

        return deleted


class InMemoryEventStore(EventStore):
    """
    Simple in-memory event store for development/testing.

    Not suitable for production multi-pod deployments.
    """

    def __init__(self, max_events_per_stream: int = 100):
        self.max_events = max_events_per_stream
        self._streams: dict[StreamId, list[tuple[EventId, JSONRPCMessage | None]]] = {}
        self._counter = 0

    async def store_event(
        self,
        stream_id: StreamId,
        message: JSONRPCMessage | None,
    ) -> EventId:
        """Store event in memory."""
        if stream_id not in self._streams:
            self._streams[stream_id] = []

        self._counter += 1
        event_id = f"{stream_id}:{self._counter}"

        self._streams[stream_id].append((event_id, message))

        # Trim old events
        if len(self._streams[stream_id]) > self.max_events:
            self._streams[stream_id] = self._streams[stream_id][-self.max_events:]

        return event_id

    async def replay_events_after(
        self,
        last_event_id: EventId,
        send_callback: EventCallback,
    ) -> StreamId | None:
        """Replay events from memory."""
        try:
            stream_id, counter_str = last_event_id.rsplit(":", 1)
            last_counter = int(counter_str)
        except (ValueError, AttributeError):
            return None

        if stream_id not in self._streams:
            return None

        events = self._streams[stream_id]
        replayed = False

        for event_id, message in events:
            _, counter_str = event_id.rsplit(":", 1)
            if int(counter_str) > last_counter:
                if hasattr(message, "model_dump"):
                    msg_dict = message.model_dump()
                elif hasattr(message, "dict"):
                    msg_dict = message.dict()
                else:
                    msg_dict = message

                event_message = EventMessage(
                    event_id=event_id,
                    message=msg_dict,
                )
                await send_callback(event_message)
                replayed = True

        return stream_id if replayed else None
