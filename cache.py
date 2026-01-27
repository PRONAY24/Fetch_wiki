"""
Redis Caching Module for Wikipedia Search Agent
================================================

This module implements the Cache-Aside pattern:
1. Check cache first
2. If miss, fetch from source
3. Store result in cache with TTL

Key Concepts:
- TTL (Time-To-Live): How long data stays in cache
- Cache Key: Unique identifier for cached data
- Serialization: Converting Python objects to storable format
"""

import os
import json
import hashlib
import logging
from typing import Optional, Any, Callable
from functools import wraps

logger = logging.getLogger(__name__)

# Redis configuration from environment
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))
CACHE_TTL = int(os.environ.get("CACHE_TTL", "3600"))  # Default: 1 hour

# Redis client - initialized lazily
_redis_client = None


def get_redis_client():
    """
    Get or create Redis client (Singleton pattern).
    
    Returns None if Redis is not available (graceful degradation).
    """
    global _redis_client
    
    if _redis_client is not None:
        return _redis_client
    
    try:
        import redis
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            db=REDIS_DB,
            decode_responses=True,  # Return strings, not bytes
            socket_connect_timeout=2,  # Fast fail if Redis is down
        )
        # Test connection
        _redis_client.ping()
        logger.info(f"✅ Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        return _redis_client
    except ImportError:
        logger.warning("⚠️ Redis package not installed. Caching disabled.")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Could not connect to Redis: {e}. Caching disabled.")
        return None


def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """
    Generate a unique cache key from function arguments.
    
    Uses MD5 hash for consistent, short keys.
    """
    key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
    hash_suffix = hashlib.md5(key_data.encode()).hexdigest()[:12]
    return f"wiki:{prefix}:{hash_suffix}"


def cache_result(prefix: str, ttl: int = None):
    """
    Decorator to cache function results in Redis.
    
    Usage:
        @cache_result("search", ttl=3600)
        def fetch_wikipedia_info(query: str) -> dict:
            ...
    
    Args:
        prefix: Cache key prefix (e.g., "search", "sections")
        ttl: Time-to-live in seconds (default: CACHE_TTL from env)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            redis_client = get_redis_client()
            cache_ttl = ttl or CACHE_TTL
            
            # If Redis is not available, call function directly
            if redis_client is None:
                return func(*args, **kwargs)
            
            # Generate cache key
            cache_key = generate_cache_key(prefix, *args, **kwargs)
            
            # Try to get from cache
            try:
                cached = redis_client.get(cache_key)
                if cached:
                    logger.info(f"🎯 Cache HIT: {cache_key}")
                    result = json.loads(cached)
                    result["_cached"] = True  # Mark as cached response
                    return result
                logger.info(f"💨 Cache MISS: {cache_key}")
            except Exception as e:
                logger.warning(f"Cache read error: {e}")
            
            # Call the actual function
            result = func(*args, **kwargs)
            
            # Store in cache (only if no error)
            if "error" not in result:
                try:
                    redis_client.setex(
                        cache_key,
                        cache_ttl,
                        json.dumps(result)
                    )
                    logger.info(f"💾 Cached: {cache_key} (TTL: {cache_ttl}s)")
                except Exception as e:
                    logger.warning(f"Cache write error: {e}")
            
            return result
        return wrapper
    return decorator


def get_cache_stats() -> dict:
    """
    Get cache statistics for monitoring.
    
    Returns:
        dict with cache info or error message
    """
    redis_client = get_redis_client()
    
    if redis_client is None:
        return {"status": "disabled", "message": "Redis not connected"}
    
    try:
        info = redis_client.info("stats")
        memory = redis_client.info("memory")
        
        # Count wiki-related keys
        wiki_keys = len(redis_client.keys("wiki:*"))
        
        return {
            "status": "connected",
            "host": f"{REDIS_HOST}:{REDIS_PORT}",
            "wiki_cached_items": wiki_keys,
            "total_hits": info.get("keyspace_hits", 0),
            "total_misses": info.get("keyspace_misses", 0),
            "memory_used": memory.get("used_memory_human", "unknown"),
            "ttl_seconds": CACHE_TTL,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def clear_cache(pattern: str = "wiki:*") -> int:
    """
    Clear cached items matching a pattern.
    
    Args:
        pattern: Redis key pattern to match (default: all wiki keys)
    
    Returns:
        Number of keys deleted
    """
    redis_client = get_redis_client()
    
    if redis_client is None:
        return 0
    
    try:
        keys = redis_client.keys(pattern)
        if keys:
            deleted = redis_client.delete(*keys)
            logger.info(f"🗑️ Cleared {deleted} cached items matching '{pattern}'")
            return deleted
        return 0
    except Exception as e:
        logger.error(f"Cache clear error: {e}")
        return 0
