# 🎓 Deep Dive: Understanding the Wikipedia Agent Architecture

This guide explains **everything** about how Phase 1 (Caching) and Phase 2 (Database) work,
including decorators, async/await, and the complete request flow.

---

## 📚 Table of Contents

1. [The Complete Request Flow](#the-complete-request-flow)
2. [Understanding Decorators](#understanding-decorators)
3. [Understanding Async/Await](#understanding-asyncawait)
4. [Phase 1: Redis Caching Deep Dive](#phase-1-redis-caching-deep-dive)
5. [Phase 2: Database Deep Dive](#phase-2-database-deep-dive)

---

## The Complete Request Flow

Let's trace what happens when you send a chat message:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         USER SENDS MESSAGE                                   │
│                    "Tell me about Python"                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: HTTP Request arrives at FastAPI                                      │
│                                                                              │
│   POST /api/chat                                                             │
│   Body: {"message": "Tell me about Python", "thread_id": "session-123"}     │
│                                                                              │
│   FastAPI routes this to the chat() function in mcp_client.py               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: LangGraph Agent processes the message                                │
│                                                                              │
│   result = await _agent.ainvoke({"messages": "Tell me about Python"})       │
│                                                                              │
│   The agent decides: "I need to search Wikipedia for Python"                │
│   It calls the fetch_wikipedia_info() tool                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Cache Check (Phase 1)                                                │
│                                                                              │
│   The @cache_result decorator intercepts the call:                           │
│                                                                              │
│   @cache_result("search", ttl=3600)    ◄── This is the decorator             │
│   def fetch_wikipedia_info(query):                                           │
│       ...                                                                    │
│                                                                              │
│   Decorator does:                                                            │
│   1. Generate key: "wiki:search:e3b0c44..." (hash of "Python")              │
│   2. Check Redis: GET wiki:search:e3b0c44...                                │
│   3. If found → Return cached result (CACHE HIT!)                           │
│   4. If not found → Continue to Step 4 (CACHE MISS)                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                         (Cache Miss) ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 4: Wikipedia API Call                                                   │
│                                                                              │
│   The original function runs:                                                │
│   - Calls Wikipedia's API                                                    │
│   - Gets title, summary, URL                                                │
│   - Returns result                                                          │
│                                                                              │
│   The decorator then:                                                        │
│   - Stores result in Redis: SETEX wiki:search:e3b0c44... 3600 {json}       │
│   - Returns result to caller                                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 5: LangGraph Agent formulates response                                  │
│                                                                              │
│   Agent receives Wikipedia data and generates:                              │
│   "Python is a high-level programming language..."                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 6: Save to Database (Phase 2)                                           │
│                                                                              │
│   async with get_session() as session:                                      │
│       repo = ConversationRepository(session)                                │
│       await repo.add_message(thread_id, USER, "Tell me about Python")       │
│       await repo.add_message(thread_id, ASSISTANT, response)                │
│                                                                              │
│   This saves the conversation for history!                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 7: Return Response to User                                              │
│                                                                              │
│   return ChatResponse(response="Python is a high-level...")                 │
│                                                                              │
│   HTTP 200 OK                                                               │
│   {"response": "Python is a high-level programming language..."}           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Understanding Decorators

### What IS a Decorator?

A decorator is a function that **wraps another function** to add extra behavior
without modifying the original function's code.

Think of it like gift wrapping:
- The gift (original function) stays the same
- The wrapping (decorator) adds presentation
- The recipient sees both together

### Decorator Basics (Step by Step)

```python
# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: A Simple Function
# ══════════════════════════════════════════════════════════════════════════════

def greet(name):
    return f"Hello, {name}!"

print(greet("Alice"))  # Output: Hello, Alice!


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: A Simple Decorator (Manual Approach)
# ══════════════════════════════════════════════════════════════════════════════

def make_fancy(func):
    """This is a decorator - it takes a function and returns a new function."""
    
    def wrapper(name):
        # Add behavior BEFORE
        print("✨ About to greet...")
        
        # Call the ORIGINAL function
        result = func(name)
        
        # Add behavior AFTER
        print("✨ Greeting complete!")
        
        return result
    
    return wrapper  # Return the new wrapped function

# Apply the decorator MANUALLY
fancy_greet = make_fancy(greet)
fancy_greet("Alice")
# Output:
# ✨ About to greet...
# Hello, Alice!
# ✨ Greeting complete!


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Using @ Syntax (Syntactic Sugar)
# ══════════════════════════════════════════════════════════════════════════════

@make_fancy                    # This is EXACTLY the same as: greet = make_fancy(greet)
def greet(name):
    return f"Hello, {name}!"

greet("Bob")
# Output:
# ✨ About to greet...
# Hello, Bob!
# ✨ Greeting complete!


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Decorator WITH Arguments (Like @cache_result("search", ttl=3600))
# ══════════════════════════════════════════════════════════════════════════════

# When a decorator has arguments, we need THREE levels of nesting:
# 1. Outer function - receives decorator arguments
# 2. Middle function - receives the function to wrap
# 3. Inner function - the actual wrapper that runs

def repeat(times):            # Level 1: Receives decorator arguments
    """Decorator that repeats a function N times."""
    
    def decorator(func):      # Level 2: Receives the function
        
        def wrapper(*args):   # Level 3: The wrapper that runs
            for i in range(times):
                result = func(*args)
            return result
        
        return wrapper
    
    return decorator

@repeat(times=3)              # repeat(3) returns decorator, which wraps say_hello
def say_hello(name):
    print(f"Hello, {name}!")

say_hello("Charlie")
# Output:
# Hello, Charlie!
# Hello, Charlie!
# Hello, Charlie!
```

### How @cache_result Works (From Your cache.py)

```python
# ══════════════════════════════════════════════════════════════════════════════
# THE ACTUAL CACHE DECORATOR (Simplified for understanding)
# ══════════════════════════════════════════════════════════════════════════════

def cache_result(prefix: str, ttl: int = 3600):
    """
    Level 1: Receives decorator arguments
    
    @cache_result("search", ttl=3600)
         ↑            ↑         ↑
       function    prefix      ttl
    
    This is called ONCE when Python loads the file.
    """
    
    def decorator(func):
        """
        Level 2: Receives the function to wrap
        
        func = fetch_wikipedia_info (the original function)
        
        This is called ONCE when the decorator is applied.
        """
        
        @wraps(func)  # Preserves original function's name and docstring
        def wrapper(*args, **kwargs):
            """
            Level 3: The wrapper that runs EVERY TIME you call the function
            
            This is called EVERY TIME someone calls fetch_wikipedia_info()
            """
            
            # Get Redis client
            redis_client = get_redis_client()
            
            # If Redis not available, just call original function
            if redis_client is None:
                return func(*args, **kwargs)
            
            # Generate unique cache key from arguments
            # e.g., "wiki:search:e3b0c44298fc1c149afbf4c8996fb924"
            cache_key = generate_cache_key(prefix, *args, **kwargs)
            
            # TRY TO GET FROM CACHE
            try:
                cached = redis_client.get(cache_key)
                if cached:
                    # CACHE HIT! Return cached data without calling Wikipedia
                    print(f"🎯 Cache HIT: {cache_key}")
                    return json.loads(cached)
                print(f"💨 Cache MISS: {cache_key}")
            except Exception as e:
                print(f"Cache read error: {e}")
            
            # CACHE MISS - Call the original function
            result = func(*args, **kwargs)  # ← This calls fetch_wikipedia_info()
            
            # Store result in cache for next time
            if "error" not in result:
                try:
                    redis_client.setex(
                        cache_key,           # Key
                        ttl,                 # Expire after this many seconds
                        json.dumps(result)   # Value (JSON string)
                    )
                    print(f"💾 Cached: {cache_key} (TTL: {ttl}s)")
                except Exception as e:
                    print(f"Cache write error: {e}")
            
            return result
        
        return wrapper  # Return the wrapper function
    
    return decorator  # Return the decorator function


# ══════════════════════════════════════════════════════════════════════════════
# HOW IT'S USED
# ══════════════════════════════════════════════════════════════════════════════

@cache_result("search", ttl=3600)  # 1 hour cache
def fetch_wikipedia_info(query: str) -> dict:
    """Search Wikipedia - results are cached!"""
    # This only runs on CACHE MISS
    # ... Wikipedia API call here ...
    return {"title": "...", "summary": "..."}


# When you call:
fetch_wikipedia_info("Python")

# What ACTUALLY happens:
# 1. wrapper("Python") is called (from the decorator)
# 2. wrapper checks Redis for "wiki:search:abc123..."
# 3. If found → return cached data (original function NEVER runs!)
# 4. If not found → call fetch_wikipedia_info("Python")
# 5. Store result in Redis
# 6. Return result
```

### Visual: Decorator Execution Order

```
When Python loads the file:
═══════════════════════════════════════════════════════════════════════════════

@cache_result("search", ttl=3600)     ─┐
def fetch_wikipedia_info(query):       │
    ...                                │
                                       │
                                       ▼
Step 1: cache_result("search", ttl=3600) is called
        Returns: decorator function
        
Step 2: decorator(fetch_wikipedia_info) is called
        Returns: wrapper function
        
Step 3: fetch_wikipedia_info = wrapper
        (The name now points to the wrapper!)


When you call fetch_wikipedia_info("Python"):
═══════════════════════════════════════════════════════════════════════════════

fetch_wikipedia_info("Python")
        │
        └──► Actually calls wrapper("Python")
                    │
                    ├──► Check cache
                    │
                    ├──► If HIT: return cached
                    │
                    └──► If MISS: call original func() → cache → return
```

---

## Understanding Async/Await

### The Problem: Blocking I/O

```python
# ══════════════════════════════════════════════════════════════════════════════
# SYNCHRONOUS (Blocking) - BAD for web servers!
# ══════════════════════════════════════════════════════════════════════════════

import time

def get_user_from_database(user_id):
    time.sleep(0.5)  # Simulates database query taking 500ms
    return {"id": user_id, "name": "Alice"}

def get_posts_from_database(user_id):
    time.sleep(0.5)  # Another 500ms
    return [{"title": "Post 1"}, {"title": "Post 2"}]

# Handle a web request
def handle_request(user_id):
    user = get_user_from_database(user_id)    # Wait 500ms... (server frozen!)
    posts = get_posts_from_database(user_id)   # Wait 500ms more... (still frozen!)
    return {"user": user, "posts": posts}
    # Total: 1000ms, and server couldn't do ANYTHING else during this time!

# If you get 100 requests at once:
# - Synchronous: Handle one at a time = 100 seconds total!
# - The 100th user waits 100 seconds just to START their request
```

### The Solution: Async/Await

```python
# ══════════════════════════════════════════════════════════════════════════════
# ASYNCHRONOUS (Non-blocking) - GREAT for web servers!
# ══════════════════════════════════════════════════════════════════════════════

import asyncio

async def get_user_from_database(user_id):
    await asyncio.sleep(0.5)  # Simulates waiting, but doesn't block!
    return {"id": user_id, "name": "Alice"}

async def get_posts_from_database(user_id):
    await asyncio.sleep(0.5)
    return [{"title": "Post 1"}, {"title": "Post 2"}]

# Handle a web request - async version
async def handle_request(user_id):
    user = await get_user_from_database(user_id)    # Start query, yield control
    posts = await get_posts_from_database(user_id)   # Start query, yield control
    return {"user": user, "posts": posts}

# Even better - run in parallel!
async def handle_request_parallel(user_id):
    # Start BOTH queries at the same time!
    user_task = get_user_from_database(user_id)
    posts_task = get_posts_from_database(user_id)
    
    # Wait for both to complete
    user, posts = await asyncio.gather(user_task, posts_task)
    return {"user": user, "posts": posts}
    # Total: 500ms (not 1000ms!) because they ran in parallel
```

### How Async Works (Conceptually)

```
SYNCHRONOUS (Blocking):
═══════════════════════════════════════════════════════════════════════════════

Time →  0ms      500ms     1000ms    1500ms    2000ms
        │         │         │         │         │
Request1: [████████DB████████]
Request2:                    [████████DB████████]
Request3:                                        [████████DB████████]

Server handles ONE request at a time. Others must wait!


ASYNCHRONOUS (Non-blocking):
═══════════════════════════════════════════════════════════════════════════════

Time →  0ms      500ms     1000ms
        │         │         │
Request1: [start]----waiting----[complete]
Request2: [start]----waiting----[complete]
Request3: [start]----waiting----[complete]
          └── All started immediately!

Server starts all requests, then waits for all to complete.
While waiting for DB, server can do other work!
```

### The Key Insight: await = "I'm waiting, go do something else"

```python
# ══════════════════════════════════════════════════════════════════════════════
# WHAT AWAIT REALLY MEANS
# ══════════════════════════════════════════════════════════════════════════════

async def make_coffee():
    print("Starting to boil water...")
    await asyncio.sleep(3)  # ← "I'll wait here, but you can do other things"
    print("Water is ready!")
    return "☕ Coffee"

async def make_toast():
    print("Starting toaster...")
    await asyncio.sleep(2)  # ← "I'll wait here, but you can do other things"
    print("Toast is ready!")
    return "🍞 Toast"

async def make_breakfast():
    # Start both at the same time
    coffee_task = make_coffee()
    toast_task = make_toast()
    
    # Wait for both
    coffee, toast = await asyncio.gather(coffee_task, toast_task)
    
    print(f"Breakfast ready: {coffee} and {toast}")
    # Takes 3 seconds total (not 5!) because they ran in parallel

asyncio.run(make_breakfast())

# Output:
# Starting to boil water...
# Starting toaster...
# (2 seconds pass)
# Toast is ready!
# (1 more second passes)
# Water is ready!
# Breakfast ready: ☕ Coffee and 🍞 Toast
```

### Async in Your Code (database.py)

```python
# ══════════════════════════════════════════════════════════════════════════════
# FROM YOUR database.py
# ══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    This is an ASYNC context manager.
    
    The 'async with' pattern:
    - async = This function uses await inside
    - with = Automatic cleanup (like try/finally)
    """
    session = get_session_factory()()
    
    try:
        yield session          # Give session to caller
        await session.commit() # ← await: "Commit to DB, I'll wait but don't block"
    except Exception:
        await session.rollback() # ← await: "Rollback, I'll wait but don't block"
        raise
    finally:
        await session.close()  # ← await: "Close connection, don't block"


# How it's used:
async def save_message(thread_id, content):
    async with get_session() as session:  # ← "async with" for async context managers
        repo = ConversationRepository(session)
        await repo.add_message(thread_id, MessageRole.USER, content)
        # ↑ await: "Save to DB, I'll wait but server can handle other requests"
```

---

## Phase 1: Redis Caching Deep Dive

### File: cache.py - Complete Walkthrough

```python
"""
WHAT IS CACHING?
═══════════════════════════════════════════════════════════════════════════════

Caching stores frequently-used data in fast memory (Redis) instead of
fetching it from slow sources (Wikipedia API) every time.

Without cache:
  Request 1: User asks about "Python" → Call Wikipedia API (200ms)
  Request 2: User asks about "Python" → Call Wikipedia API (200ms)
  Request 3: User asks about "Python" → Call Wikipedia API (200ms)
  Total: 600ms

With cache:
  Request 1: User asks about "Python" → Call Wikipedia API (200ms) → Store in Redis
  Request 2: User asks about "Python" → Get from Redis (2ms)
  Request 3: User asks about "Python" → Get from Redis (2ms)
  Total: 204ms (3x faster!)
"""

import os
import json
import hashlib
import logging
from functools import wraps
from typing import Callable, Any

import redis

logger = logging.getLogger(__name__)

# Configuration from environment variables
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))
DEFAULT_TTL = int(os.environ.get("CACHE_TTL", "3600"))  # 1 hour default

# Global Redis client (Singleton pattern)
_redis_client = None


def get_redis_client():
    """
    Get or create Redis client (Singleton pattern).
    
    SINGLETON = Only one instance exists, shared by everyone.
    
    Why? Creating connections is expensive. We want ONE connection that
    everyone shares, not a new connection for every request.
    """
    global _redis_client
    
    if _redis_client is None:
        try:
            _redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                db=REDIS_DB,
                decode_responses=True  # Return strings, not bytes
            )
            # Test connection
            _redis_client.ping()
            logger.info(f"✅ Redis connected: {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            logger.warning(f"⚠️ Redis not available: {e}")
            return None
    
    return _redis_client


def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """
    Generate a unique cache key from function arguments.
    
    PROBLEM: We need a unique key for each unique set of arguments.
    
    Example:
      fetch_wikipedia_info("Python")     → wiki:search:abc123...
      fetch_wikipedia_info("JavaScript") → wiki:search:def456...
    
    We use a HASH (MD5) because:
    - Consistent: Same input always = same output
    - Short: Long queries become fixed-length hashes
    - Unique: Different inputs give different hashes
    """
    # Combine all arguments into a string
    key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
    
    # Hash it (MD5 is fine for cache keys, not for security)
    key_hash = hashlib.md5(key_data.encode()).hexdigest()
    
    return f"wiki:{prefix}:{key_hash}"


def cache_result(prefix: str, ttl: int = None):
    """
    Decorator to cache function results in Redis.
    
    USAGE:
        @cache_result("search", ttl=3600)
        def fetch_wikipedia_info(query):
            # This only runs on cache MISS
            return wikipedia.search(query)
    """
    cache_ttl = ttl or DEFAULT_TTL
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)  # Preserve original function's metadata
        def wrapper(*args, **kwargs) -> Any:
            redis_client = get_redis_client()
            
            # GRACEFUL DEGRADATION: If Redis is down, just call the function
            if redis_client is None:
                return func(*args, **kwargs)
            
            cache_key = generate_cache_key(prefix, *args, **kwargs)
            
            # TRY TO GET FROM CACHE
            try:
                cached = redis_client.get(cache_key)
                if cached:
                    logger.info(f"🎯 Cache HIT: {cache_key}")
                    result = json.loads(cached)
                    result["_cached"] = True  # Mark as cached (for debugging)
                    return result
                logger.info(f"💨 Cache MISS: {cache_key}")
            except Exception as e:
                logger.warning(f"Cache read error: {e}")
            
            # CACHE MISS: Call the original function
            result = func(*args, **kwargs)
            
            # Store in cache (only if no error)
            if "error" not in result:
                try:
                    redis_client.setex(
                        cache_key,        # Key
                        cache_ttl,        # TTL in seconds
                        json.dumps(result) # Value as JSON string
                    )
                    logger.info(f"💾 Cached: {cache_key} (TTL: {cache_ttl}s)")
                except Exception as e:
                    logger.warning(f"Cache write error: {e}")
            
            return result
        
        return wrapper
    
    return decorator


def get_cache_stats() -> dict:
    """Get cache statistics for the /api/cache/stats endpoint."""
    redis_client = get_redis_client()
    
    if redis_client is None:
        return {"status": "disconnected"}
    
    try:
        info = redis_client.info("memory")
        keys = redis_client.keys("wiki:*")
        
        return {
            "status": "connected",
            "host": f"{REDIS_HOST}:{REDIS_PORT}",
            "wiki_cached_items": len(keys),
            "memory_used": info.get("used_memory_human", "unknown"),
            "ttl_seconds": DEFAULT_TTL
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def clear_cache() -> int:
    """Clear all wiki cache entries. Returns count of deleted keys."""
    redis_client = get_redis_client()
    
    if redis_client is None:
        return 0
    
    keys = redis_client.keys("wiki:*")
    if keys:
        return redis_client.delete(*keys)
    return 0
```

---

## Phase 2: Database Deep Dive

### The Three Files Work Together

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           APPLICATION LAYER                                  │
│                           (mcp_client.py)                                    │
│                                                                              │
│   async with get_session() as session:                                      │
│       repo = ConversationRepository(session)   ◄── Uses Repository          │
│       await repo.add_message(...)                                           │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           REPOSITORY LAYER                                   │
│                           (repository.py)                                    │
│                                                                              │
│   class ConversationRepository:                                             │
│       async def add_message(self, ...):        ◄── Knows HOW to save        │
│           conversation = await self.get_or_create_conversation(...)         │
│           message = Message(...)                ◄── Uses Models             │
│           self.session.add(message)                                         │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MODEL LAYER                                        │
│                           (models.py)                                        │
│                                                                              │
│   class Conversation(Base):                    ◄── Defines WHAT data        │
│       id, thread_id, title, created_at...                                   │
│                                                                              │
│   class Message(Base):                                                       │
│       id, conversation_id, role, content...                                 │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATABASE LAYER                                     │
│                           (database.py)                                      │
│                                                                              │
│   Engine (connection pool)                     ◄── Manages connections      │
│   Session (transaction boundary)                                             │
│   PostgreSQL                                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Reference Card

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                           QUICK REFERENCE                                      ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                                ║
║  DECORATORS                                                                    ║
║  ─────────────────────────────────────────────────────────────────────────    ║
║  @decorator              = Wraps a function to add behavior                   ║
║  @decorator(args)        = Decorator with configuration                       ║
║  @wraps(func)            = Preserves original function's name/docs            ║
║                                                                                ║
║  ASYNC/AWAIT                                                                   ║
║  ─────────────────────────────────────────────────────────────────────────    ║
║  async def func()        = This function is asynchronous                      ║
║  await something()       = Wait for this, but don't block the server         ║
║  async with              = Async context manager (auto cleanup)               ║
║  asyncio.gather()        = Run multiple async tasks in parallel               ║
║                                                                                ║
║  REDIS COMMANDS                                                                ║
║  ─────────────────────────────────────────────────────────────────────────    ║
║  GET key                 = Retrieve value                                     ║
║  SETEX key ttl value     = Store with expiration                             ║
║  KEYS pattern            = Find keys matching pattern                        ║
║  DEL key                 = Delete key                                         ║
║                                                                                ║
║  SQLALCHEMY                                                                    ║
║  ─────────────────────────────────────────────────────────────────────────    ║
║  session.add(obj)        = Mark for INSERT                                   ║
║  session.delete(obj)     = Mark for DELETE                                   ║
║  await session.commit()  = Save all changes                                   ║
║  await session.rollback()= Undo all changes                                   ║
║  await session.execute() = Run a query                                        ║
║                                                                                ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

---

## 🧪 Try It Yourself

Run these commands on your VM to see everything in action:

```bash
# See cache in action (run twice - first is MISS, second is HIT)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me about JavaScript", "thread_id": "test-deep-dive"}'

# Check cache stats
curl http://localhost:8000/api/cache/stats

# Check database stats
curl http://localhost:8000/api/db/stats

# View your conversation history
curl http://localhost:8000/api/conversations

# Get messages from a specific conversation
curl http://localhost:8000/api/conversations/test-deep-dive/messages
```

---

**Questions?** Let me know which part you'd like to explore further!
