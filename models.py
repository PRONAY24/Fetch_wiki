"""
Database Models for Wikipedia Search Agent
==========================================

PHASE 2: Database Persistence with PostgreSQL

=== WHAT IS THIS FILE? ===
This file defines the "shape" of your database tables using Python classes.
Instead of writing SQL like "CREATE TABLE conversations...", you write Python
classes and SQLAlchemy automatically creates the tables for you.

=== KEY CONCEPT: ORM (Object-Relational Mapping) ===
ORM is a technique that lets you interact with your database using Python
objects instead of writing raw SQL queries. It's like having a translator
between Python and SQL.

Python Class (this file)  <-->  ORM (SQLAlchemy)  <-->  Database Table (PostgreSQL)
     Conversation         <-->     translates     <-->     conversations table

=== WHY USE ORM? ===
1. Write Python, not SQL - easier to read and maintain
2. Database-agnostic - switch from PostgreSQL to MySQL easily
3. Automatic validation - catches errors before they hit the database
4. Relationships - easily link tables together (conversation has many messages)
"""

from datetime import datetime
from typing import Optional, List

# SQLAlchemy imports
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


# =============================================================================
# BASE CLASS
# =============================================================================

class Base(DeclarativeBase):
    """
    Base class that all our models inherit from.
    
    Think of this as the "parent" class that gives all our database
    tables common functionality. SQLAlchemy requires this.
    """
    pass


# =============================================================================
# ENUMS (Fixed choices)
# =============================================================================

class MessageRole(str, enum.Enum):
    """
    Who sent the message? This is an ENUM - a fixed set of choices.
    
    Why use an enum instead of a string?
    - Prevents typos: "user" is valid, "usr" would cause an error
    - Makes code clearer: MessageRole.USER vs "user"
    - Database stores efficiently as integers
    """
    USER = "user"           # Message from the human user
    ASSISTANT = "assistant" # Message from the AI assistant
    SYSTEM = "system"       # System instructions (rarely used)


# =============================================================================
# CONVERSATION MODEL
# =============================================================================

class Conversation(Base):
    """
    Represents a chat session.
    
    === DATABASE TABLE ===
    This class becomes a table called "conversations" with these columns:
    
    | id | thread_id      | title              | created_at          | updated_at          |
    |----|----------------|--------------------|---------------------|---------------------|
    | 1  | session-12345  | Tell me about...   | 2024-01-28 10:00:00 | 2024-01-28 10:05:00 |
    | 2  | session-67890  | What is quantum... | 2024-01-28 11:00:00 | 2024-01-28 11:10:00 |
    
    === RELATIONSHIPS ===
    One Conversation has MANY Messages (1:N relationship)
    """
    
    # Table name in the database
    __tablename__ = "conversations"
    
    # PRIMARY KEY: Unique identifier for each row
    # autoincrement=True means the database auto-generates this (1, 2, 3, ...)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # The thread_id from the frontend (e.g., "session-1706434208000")
    # unique=True: No two conversations can have the same thread_id
    # index=True: Makes searching by thread_id faster
    thread_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    
    # Optional title, auto-set from the first message
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Timestamps - automatically set when creating/updating
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # RELATIONSHIP: Link to Message objects
    # back_populates: Creates a two-way link (conversation.messages <-> message.conversation)
    # cascade="all, delete-orphan": If we delete a conversation, delete its messages too
    messages: Mapped[List["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        """How this object appears when printed (for debugging)."""
        return f"<Conversation(id={self.id}, thread_id='{self.thread_id}')>"


# =============================================================================
# MESSAGE MODEL
# =============================================================================

class Message(Base):
    """
    Represents a single message in a conversation.
    
    === DATABASE TABLE ===
    | id | conversation_id | role      | content              | created_at          |
    |----|-----------------|-----------|----------------------|---------------------|
    | 1  | 1               | user      | Tell me about Python | 2024-01-28 10:00:00 |
    | 2  | 1               | assistant | Python is a...       | 2024-01-28 10:00:05 |
    
    === FOREIGN KEY ===
    conversation_id links to the conversations table.
    This is how we know which messages belong to which conversation.
    """
    
    __tablename__ = "messages"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # FOREIGN KEY: Links this message to a conversation
    # ON DELETE CASCADE: If the conversation is deleted, delete this message too
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), 
        index=True  # Faster lookups by conversation
    )
    
    # Who sent this message?
    role: Mapped[MessageRole] = mapped_column(SQLEnum(MessageRole))
    
    # The actual message content (Text = unlimited length)
    content: Mapped[str] = mapped_column(Text)
    
    # When was this message created?
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Optional: Track API token usage for cost monitoring
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # RELATIONSHIP: Link back to the parent conversation
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )
    
    def __repr__(self) -> str:
        # Truncate content to 30 chars for readability
        return f"<Message(id={self.id}, role='{self.role}', content='{self.content[:30]}...')>"


# =============================================================================
# CACHED SEARCH MODEL (Bonus!)
# =============================================================================

class CachedSearch(Base):
    """
    Persistent cache for Wikipedia searches.
    
    This complements Redis (Phase 1) by providing a database backup.
    If Redis goes down, we can still serve cached results from PostgreSQL.
    
    | id | query_hash   | query           | result_json | expires_at |
    |----|-------------|-----------------|-------------|------------|
    | 1  | abc123...   | Python language | {...}       | 2024-01-29 |
    """
    
    __tablename__ = "cached_searches"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Hash of the query for fast lookups
    query_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    # Original query text
    query: Mapped[str] = mapped_column(String(500))
    
    # JSON-encoded search results
    result_json: Mapped[str] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    
    def __repr__(self) -> str:
        return f"<CachedSearch(query='{self.query[:30]}...')>"
