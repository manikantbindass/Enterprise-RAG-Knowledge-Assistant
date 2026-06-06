"""
Redis cache client with async get/set/delete, decorator support, and pub/sub.

Wraps redis.asyncio (redis-py async) with:
- Type-safe JSON serialization / deserialization
- @cached decorator for async functions
- Pub/Sub channels for real-time notifications
- Connection pool managed by the Redis client

Usage (direct):
    cache = RedisCache(redis_url="redis://localhost:6379/0")
    await cache.set("key", {"data": 123}, expire=300)
    value = await cache.get("key")  # {"data": 123} or None

Usage (decorator):
    @cached(key_prefix="user_profile", expire_seconds=300)
    async def get_user_profile(user_id: str) -> dict:
        return await db.fetch_user(user_id)

Usage (pub/sub):
    # Publisher
    await cache.publish("events", {"type": "document.indexed", "id": doc_id})

    # Subscriber
    async for message in cache.subscribe("events"):
        handle(message)
"""

from __future__ import annotations

import functools
import json
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Optional, TypeVar

import structlog
from redis.asyncio import Redis, ConnectionPool
from redis.asyncio.client import PubSub

logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _serialize(value: Any) -> str:
    """JSON-serialize a value for Redis storage."""
    return json.dumps(value, default=_json_default)


def _deserialize(raw: str) -> Any:
    """JSON-deserialize a value from Redis storage."""
    return json.loads(raw)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not JSON serializable")


class RedisCache:
    """
    Async Redis client wrapper.

    Manages a shared ConnectionPool for efficiency.
    All methods are async and safe for concurrent use.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        *,
        max_connections: int = 50,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 2.0,
        decode_responses: bool = True,
    ) -> None:
        self._pool = ConnectionPool.from_url(
            redis_url,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            decode_responses=decode_responses,
        )
        self._client = Redis(connection_pool=self._pool)
        logger.info("redis_cache_initialized", max_connections=max_connections)

    @property
    def client(self) -> Redis:
        """Raw redis.asyncio.Redis client for advanced operations."""
        return self._client

    async def get(self, key: str) -> Any | None:
        """
        Get a value from Redis.

        Args:
            key: Cache key.

        Returns:
            Deserialized value or None if key missing/expired.
        """
        try:
            raw = await self._client.get(key)
            if raw is None:
                return None
            return _deserialize(raw)
        except Exception as exc:
            logger.error("cache_get_error", key=key, error=str(exc))
            return None

    async def set(
        self,
        key: str,
        value: Any,
        *,
        expire: int | None = None,
        nx: bool = False,
    ) -> bool:
        """
        Set a value in Redis.

        Args:
            key: Cache key.
            value: Value to cache (must be JSON-serializable).
            expire: TTL in seconds. None = no expiry.
            nx: If True, only set if key does NOT exist (SETNX).

        Returns:
            True on success.
        """
        try:
            serialized = _serialize(value)
            result = await self._client.set(key, serialized, ex=expire, nx=nx)
            return bool(result)
        except Exception as exc:
            logger.error("cache_set_error", key=key, error=str(exc))
            return False

    async def delete(self, *keys: str) -> int:
        """
        Delete one or more keys.

        Returns:
            Number of keys deleted.
        """
        try:
            return await self._client.delete(*keys)
        except Exception as exc:
            logger.error("cache_delete_error", keys=keys, error=str(exc))
            return 0

    async def exists(self, key: str) -> bool:
        """Return True if key exists in Redis."""
        try:
            return bool(await self._client.exists(key))
        except Exception as exc:
            logger.error("cache_exists_error", key=key, error=str(exc))
            return False

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiry on an existing key."""
        try:
            return bool(await self._client.expire(key, seconds))
        except Exception as exc:
            logger.error("cache_expire_error", key=key, error=str(exc))
            return False

    async def incr(self, key: str, amount: int = 1) -> int | None:
        """Atomic increment. Returns new value."""
        try:
            return await self._client.incr(key, amount)
        except Exception as exc:
            logger.error("cache_incr_error", key=key, error=str(exc))
            return None

    async def hset(self, name: str, mapping: dict[str, Any]) -> int:
        """Set multiple hash fields."""
        try:
            serialized = {k: _serialize(v) for k, v in mapping.items()}
            return await self._client.hset(name, mapping=serialized)
        except Exception as exc:
            logger.error("cache_hset_error", name=name, error=str(exc))
            return 0

    async def hget(self, name: str, key: str) -> Any | None:
        """Get a hash field value."""
        try:
            raw = await self._client.hget(name, key)
            return _deserialize(raw) if raw is not None else None
        except Exception as exc:
            logger.error("cache_hget_error", name=name, key=key, error=str(exc))
            return None

    async def hgetall(self, name: str) -> dict[str, Any]:
        """Get all hash fields."""
        try:
            raw = await self._client.hgetall(name)
            return {k: _deserialize(v) for k, v in raw.items()}
        except Exception as exc:
            logger.error("cache_hgetall_error", name=name, error=str(exc))
            return {}

    async def publish(self, channel: str, message: dict[str, Any]) -> int:
        """
        Publish a message to a Redis pub/sub channel.

        Args:
            channel: Channel name.
            message: Dict payload — JSON-serialized before publish.

        Returns:
            Number of subscribers that received the message.
        """
        try:
            serialized = _serialize(message)
            count = await self._client.publish(channel, serialized)
            logger.debug("cache_publish", channel=channel, receivers=count)
            return count
        except Exception as exc:
            logger.error("cache_publish_error", channel=channel, error=str(exc))
            return 0

    async def subscribe(
        self, *channels: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Subscribe to one or more Redis pub/sub channels.

        Yields deserialized message dicts.
        Caller must cancel the generator to unsubscribe.

        Usage:
            async for msg in cache.subscribe("notifications"):
                print(msg)
        """
        pubsub: PubSub = self._client.pubsub()
        await pubsub.subscribe(*channels)
        logger.info("cache_subscribed", channels=channels)

        try:
            async for raw_message in pubsub.listen():
                if raw_message["type"] == "message":
                    try:
                        yield _deserialize(raw_message["data"])
                    except Exception as exc:
                        logger.error(
                            "cache_subscribe_deserialize_error",
                            error=str(exc),
                            raw=raw_message.get("data"),
                        )
        finally:
            await pubsub.unsubscribe(*channels)
            await pubsub.close()
            logger.info("cache_unsubscribed", channels=channels)

    async def close(self) -> None:
        """Close Redis connection pool."""
        await self._client.aclose()
        logger.info("redis_cache_closed")


# ---------------------------------------------------------------------------
# @cached decorator
# ---------------------------------------------------------------------------


def cached(
    key_prefix: str,
    *,
    expire_seconds: int = 300,
    key_builder: Callable[..., str] | None = None,
) -> Callable[[F], F]:
    """
    Decorator to cache async function results in Redis.

    Cache key is built from key_prefix + stringified positional args.
    Provide key_builder for custom key logic.

    Requires the decorated function to have access to a RedisCache instance.
    The cache instance must be the first argument named 'cache', OR
    the function's first argument must have a .cache attribute.

    Simple approach: inject cache via closure or partial.

    Usage:
        cache = RedisCache(redis_url)

        @cached("user", expire_seconds=300)
        async def get_user(cache: RedisCache, user_id: str) -> dict:
            return await fetch_from_db(user_id)

        # Call normally:
        user = await get_user(cache, user_id)

    Args:
        key_prefix: Cache key prefix.
        expire_seconds: TTL in seconds.
        key_builder: Optional function(args, kwargs) -> str for custom keys.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Find RedisCache in args
            cache_instance: RedisCache | None = None
            for arg in args:
                if isinstance(arg, RedisCache):
                    cache_instance = arg
                    break

            # Build cache key
            if key_builder:
                cache_key = key_builder(args, kwargs)
            else:
                # Use args after the cache instance as key parts
                key_parts = [
                    str(a) for a in args if not isinstance(a, RedisCache)
                ]
                key_parts += [f"{k}={v}" for k, v in sorted(kwargs.items())]
                cache_key = f"{key_prefix}:{':'.join(key_parts)}"

            if cache_instance:
                cached_value = await cache_instance.get(cache_key)
                if cached_value is not None:
                    logger.debug("cache_hit", key=cache_key)
                    return cached_value

            result = await func(*args, **kwargs)

            if cache_instance and result is not None:
                await cache_instance.set(cache_key, result, expire=expire_seconds)
                logger.debug("cache_set", key=cache_key, ttl=expire_seconds)

            return result

        return wrapper  # type: ignore[return-value]

    return decorator
