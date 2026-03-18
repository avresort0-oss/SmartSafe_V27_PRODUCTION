"""
SmartSafe V27 - Redis Cache Module
Provides Redis-based caching for analytics and other data.
"""

import json
import logging
from typing import Any, Optional
import redis

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis cache wrapper with JSON serialization."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
    ):
        self.redis_client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        self._test_connection()

    def _test_connection(self):
        """Test Redis connection on initialization."""
        try:
            self.redis_client.ping()
            logger.info("Redis cache connected successfully")
        except redis.ConnectionError as e:
            logger.warning(f"Redis connection failed: {e}. Falling back to no caching.")
            self.redis_client = None

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self.redis_client:
            return None
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in cache with optional TTL."""
        if not self.redis_client:
            return
        try:
            json_value = json.dumps(value)
            if ttl:
                self.redis_client.setex(key, ttl, json_value)
            else:
                self.redis_client.set(key, json_value)
        except Exception as e:
            logger.error(f"Redis set error: {e}")

    def delete(self, key: str):
        """Delete key from cache."""
        if not self.redis_client:
            return
        try:
            self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"Redis delete error: {e}")

    def clear_all(self):
        """Clear all cache entries."""
        if not self.redis_client:
            return
        try:
            self.redis_client.flushdb()
            logger.info("Redis cache cleared")
        except Exception as e:
            logger.error(f"Redis clear error: {e}")

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        if not self.redis_client:
            return False
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False


# Global cache instance
_cache_instance: Optional[RedisCache] = None


def get_redis_cache() -> Optional[RedisCache]:
    """Get global Redis cache instance."""
    return _cache_instance


def init_redis_cache(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None,
):
    """Initialize global Redis cache."""
    global _cache_instance
    try:
        _cache_instance = RedisCache(host, port, db, password)
    except Exception as e:
        logger.error(f"Failed to initialize Redis cache: {e}")
        _cache_instance = None
