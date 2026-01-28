"""
Database Connection Module for Wikipedia Search Agent
=====================================================

PHASE 2: Database Persistence with PostgreSQL

=== WHAT IS THIS FILE? ===
This file manages HOW we connect to the database. It handles:
1. Creating the database connection (engine)
2. Managing a pool of connections for efficiency
3. Providing sessions for database operations
4. Initializing tables on startup

=== KEY CONCEPT: CONNECTION POOLING ===

Without pooling:
  Request 1: Connect → Query → Disconnect (50ms)
  Request 2: Connect → Query → Disconnect (50ms)
  Request 3: Connect → Query → Disconnect (50ms)
  Total: 150ms just for connections!

With pooling:
  Startup: Create 5 connections and keep them open
  Request 1: Borrow connection → Query → Return (5ms)
  Request 2: Borrow connection → Query → Return (5ms)
  Request 3: Borrow connection → Query → Return (5ms)
  Total: 15ms - 10x faster!

=== KEY CONCEPT: ASYNC/AWAIT ===

Synchronous (blocking):
  Database query starts... (server waits, can't do anything else)
  Database query finishes

Asynchronous (non-blocking):
  Database query starts... (server handles other requests while waiting)
  Database query finishes

This is crucial for web servers handling many concurrent requests!
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# SQLAlchemy async imports
from sqlalchemy.ext.asyncio import (
    AsyncSession,          # Async version of database session
    AsyncEngine,           # Async version of database engine
    create_async_engine,   # Creates async engine
    async_sessionmaker     # Creates sessions in async context
)

from models import Base   # Import our models to create tables

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION (from environment variables)
# =============================================================================

# Database URL format: dialect+driver://username:password@host:port/database
# - dialect: postgresql (the database type)
# - driver: asyncpg (async PostgreSQL driver)
# - username:password: Database credentials
# - host:port: Where PostgreSQL is running
# - database: Database name
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/wikipedia_agent"
)

# Connection pool settings
# POOL_SIZE: Number of connections to keep open permanently
# MAX_OVERFLOW: Additional connections allowed during high load
# Total max connections = POOL_SIZE + MAX_OVERFLOW = 15
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "10"))


# =============================================================================
# GLOBAL STATE (Singleton Pattern)
# =============================================================================

# We only want ONE engine and ONE session factory for the entire application
# This is called the Singleton pattern - ensures a single shared instance
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


# =============================================================================
# ENGINE (Database Connection)
# =============================================================================

def get_engine() -> AsyncEngine:
    """
    Get or create the database engine.
    
    The ENGINE is like a "connection factory" - it manages the pool of
    database connections. You typically have ONE engine per application.
    
    === WHAT IS AN ENGINE? ===
    Think of it as the "gateway" to your database:
    
    Your Python App  --->  Engine (manages connections)  --->  PostgreSQL
                              |
                              v
                      Connection Pool
                      [conn1] [conn2] [conn3] [conn4] [conn5]
    """
    global _engine
    
    if _engine is None:
        logger.info(f"Creating database engine with pool_size={POOL_SIZE}")
        _engine = create_async_engine(
            DATABASE_URL,
            
            # Pool settings
            pool_size=POOL_SIZE,        # Keep 5 connections open
            max_overflow=MAX_OVERFLOW,  # Allow 10 more during peak load
            
            # Health check: Test connections before using
            # This prevents "connection is closed" errors
            pool_pre_ping=True,
            
            # Debug mode: Print all SQL queries (useful for learning!)
            echo=os.environ.get("DB_ECHO", "false").lower() == "true",
        )
    
    return _engine


# =============================================================================
# SESSION FACTORY
# =============================================================================

def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get or create the session factory.
    
    === WHAT IS A SESSION? ===
    A session is like a "shopping cart" for database operations:
    
    1. Open session (start shopping)
    2. Add operations (add items to cart)
    3. Commit (checkout - save all changes)
    4. Or rollback (abandon cart - undo all changes)
    
    === SESSION FACTORY ===
    The factory creates new sessions. Each web request gets its own session.
    """
    global _session_factory
    
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),              # Use our engine
            class_=AsyncSession,       # Create async sessions
            expire_on_commit=False,    # Keep data after commit
        )
    
    return _session_factory


# =============================================================================
# SESSION CONTEXT MANAGER
# =============================================================================

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions.
    
    === WHAT IS A CONTEXT MANAGER? ===
    The "async with" pattern automatically handles setup and cleanup:
    
        async with get_session() as session:
            # This code runs with a valid session
            result = await session.execute(query)
        # Session is automatically closed here, even if there's an error!
    
    === TRANSACTION HANDLING ===
    - If everything succeeds → commit (save changes)
    - If an exception occurs → rollback (undo changes)
    
    This ensures your database is never left in a broken state!
    """
    session = get_session_factory()()
    
    try:
        yield session              # Give the session to the caller
        await session.commit()     # Success! Save all changes
    except Exception:
        await session.rollback()   # Error! Undo all changes
        raise                      # Re-raise the exception
    finally:
        await session.close()      # Always clean up


# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================

async def init_database() -> None:
    """
    Initialize the database by creating all tables.
    
    Called once on application startup. Creates tables based on your models:
    - Conversation → conversations table
    - Message → messages table
    - CachedSearch → cached_searches table
    
    If tables already exist, this does nothing (safe to call multiple times).
    """
    engine = get_engine()
    
    try:
        async with engine.begin() as conn:
            # Create all tables defined in models.py
            # run_sync is needed because create_all is synchronous
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables created successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        raise


# =============================================================================
# CLEANUP
# =============================================================================

async def close_database() -> None:
    """
    Close the database engine and clean up connections.
    
    Called on application shutdown. Important to:
    - Close all open connections
    - Free up database resources
    - Allow graceful application restart
    """
    global _engine, _session_factory
    
    if _engine is not None:
        await _engine.dispose()    # Close all pooled connections
        _engine = None
        _session_factory = None
        logger.info("Database connections closed")


# =============================================================================
# HEALTH CHECK
# =============================================================================

async def check_database_health() -> dict:
    """
    Check database connectivity for health monitoring.
    
    Used by /api/db/stats endpoint to verify the database is working.
    
    Returns:
        dict: Status and pool info, or error details
    """
    try:
        async with get_session() as session:
            # Simple query to test connectivity
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1"))
            result.scalar()
        
        return {
            "status": "connected",
            "pool_size": POOL_SIZE,
            "max_overflow": MAX_OVERFLOW,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }
