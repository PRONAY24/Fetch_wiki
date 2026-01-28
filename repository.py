"""
Conversation Repository Module
==============================

PHASE 2: Database Persistence with PostgreSQL

=== WHAT IS THIS FILE? ===
This is the DATA ACCESS LAYER - it contains all the database queries.
It follows the REPOSITORY PATTERN, which separates:
- Business logic (what to do)
- Data access (how to get/store data)

=== WHY USE THE REPOSITORY PATTERN? ===

WITHOUT Repository (logic mixed with data access):
    @app.post("/api/chat")
    async def chat(request):
        # Business logic + SQL mixed together - messy!
        query = "SELECT * FROM conversations WHERE thread_id = ?"
        result = await db.execute(query, request.thread_id)
        ...

WITH Repository (clean separation):
    @app.post("/api/chat")
    async def chat(request):
        # Clean business logic, SQL is hidden in repository
        repo = ConversationRepository(session)
        conversation = await repo.get_or_create_conversation(request.thread_id)
        ...

=== BENEFITS ===
1. Testability: Mock the repository for unit tests
2. Maintainability: Change queries in one place
3. Readability: Business logic is clear and focused
4. Flexibility: Swap databases without changing business logic
"""

import logging
from datetime import datetime
from typing import Optional, List

# SQLAlchemy query building functions
from sqlalchemy import select, desc, func

# Session type for type hints
from sqlalchemy.ext.asyncio import AsyncSession

# Our models
from models import Conversation, Message, MessageRole

logger = logging.getLogger(__name__)


class ConversationRepository:
    """
    Repository for Conversation and Message database operations.
    
    === HOW TO USE ===
    
    async with get_session() as session:
        repo = ConversationRepository(session)
        
        # Get or create a conversation
        conversation = await repo.get_or_create_conversation("thread-123")
        
        # Add a message
        await repo.add_message("thread-123", MessageRole.USER, "Hello!")
        
        # Get history
        messages = await repo.get_conversation_history("thread-123")
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize with a database session.
        
        The session is injected (passed in) so we can:
        - Control transaction boundaries in the calling code
        - Easily mock the session for testing
        """
        self.session = session
    
    # =========================================================================
    # CONVERSATION OPERATIONS
    # =========================================================================
    
    async def get_or_create_conversation(self, thread_id: str) -> Conversation:
        """
        Get an existing conversation or create a new one.
        
        This is a common pattern called "upsert" (update or insert):
        - If conversation exists → return it
        - If not → create and return it
        
        Args:
            thread_id: Unique identifier from the frontend (e.g., "session-12345")
            
        Returns:
            Conversation object (either existing or newly created)
        
        === SQL EQUIVALENT ===
        SELECT * FROM conversations WHERE thread_id = 'session-12345';
        -- If not found:
        INSERT INTO conversations (thread_id) VALUES ('session-12345');
        """
        # Build the query using SQLAlchemy's query builder
        query = select(Conversation).where(Conversation.thread_id == thread_id)
        
        # Execute and get the result
        result = await self.session.execute(query)
        
        # scalar_one_or_none: Get one result or None
        conversation = result.scalar_one_or_none()
        
        # If not found, create new
        if conversation is None:
            conversation = Conversation(thread_id=thread_id)
            self.session.add(conversation)  # Mark for insertion
            await self.session.flush()      # Execute INSERT to get the ID
            logger.info(f"Created new conversation: {thread_id}")
        
        return conversation
    
    # =========================================================================
    # MESSAGE OPERATIONS
    # =========================================================================
    
    async def add_message(
        self,
        thread_id: str,
        role: MessageRole,
        content: str,
        tokens_used: Optional[int] = None
    ) -> Message:
        """
        Add a message to a conversation.
        
        This is called after each chat interaction to save:
        1. The user's message
        2. The assistant's response
        
        Args:
            thread_id: Which conversation to add to
            role: USER, ASSISTANT, or SYSTEM
            content: The message text
            tokens_used: Optional token count for cost tracking
            
        Returns:
            The created Message object
        
        === EXAMPLE ===
        await repo.add_message(
            "session-123",
            MessageRole.USER,
            "What is Python?"
        )
        """
        # Get or create the parent conversation
        conversation = await self.get_or_create_conversation(thread_id)
        
        # Create the message
        message = Message(
            conversation_id=conversation.id,  # Link to parent
            role=role,
            content=content,
            tokens_used=tokens_used
        )
        self.session.add(message)
        
        # Auto-set conversation title from first user message
        # This makes the conversation list more useful
        if conversation.title is None and role == MessageRole.USER:
            conversation.title = content[:100]  # First 100 chars
        
        await self.session.flush()  # Get the ID
        return message
    
    async def get_conversation_history(
        self,
        thread_id: str,
        limit: int = 50
    ) -> List[Message]:
        """
        Get recent messages from a conversation.
        
        Returns messages in chronological order (oldest first).
        
        Args:
            thread_id: Which conversation
            limit: Max messages to return (prevents huge responses)
            
        Returns:
            List of Message objects, oldest first
        
        === SQL EQUIVALENT ===
        SELECT m.* FROM messages m
        JOIN conversations c ON m.conversation_id = c.id
        WHERE c.thread_id = 'session-123'
        ORDER BY m.created_at DESC
        LIMIT 50;
        """
        query = (
            select(Message)
            .join(Conversation)                            # Join with conversations
            .where(Conversation.thread_id == thread_id)    # Filter by thread
            .order_by(Message.created_at.desc())           # Newest first
            .limit(limit)
        )
        result = await self.session.execute(query)
        messages = list(result.scalars().all())
        
        # Reverse to get chronological order (oldest first)
        return list(reversed(messages))
    
    # =========================================================================
    # LIST OPERATIONS
    # =========================================================================
    
    async def list_conversations(
        self,
        limit: int = 20,
        offset: int = 0
    ) -> List[Conversation]:
        """
        List recent conversations with pagination.
        
        Used by the UI to show conversation history.
        
        Args:
            limit: How many to return
            offset: Skip this many (for pagination)
            
        Returns:
            List of Conversation objects
        
        === PAGINATION EXAMPLE ===
        Page 1: limit=20, offset=0  → conversations 1-20
        Page 2: limit=20, offset=20 → conversations 21-40
        Page 3: limit=20, offset=40 → conversations 41-60
        """
        query = (
            select(Conversation)
            .order_by(desc(Conversation.updated_at))  # Most recent first
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    # =========================================================================
    # DELETE OPERATIONS
    # =========================================================================
    
    async def delete_conversation(self, thread_id: str) -> bool:
        """
        Delete a conversation and all its messages.
        
        Thanks to CASCADE DELETE, deleting a conversation automatically
        deletes all its messages (no orphan messages left behind).
        
        Args:
            thread_id: Which conversation to delete
            
        Returns:
            True if deleted, False if not found
        """
        query = select(Conversation).where(Conversation.thread_id == thread_id)
        result = await self.session.execute(query)
        conversation = result.scalar_one_or_none()
        
        if conversation:
            await self.session.delete(conversation)
            logger.info(f"Deleted conversation: {thread_id}")
            return True
        
        return False
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    async def get_conversation_stats(self) -> dict:
        """
        Get statistics about stored conversations.
        
        Used by /api/db/stats for monitoring.
        
        Returns:
            dict: {total_conversations: N, total_messages: M}
        """
        # Count conversations
        conv_query = select(func.count(Conversation.id))
        conv_result = await self.session.execute(conv_query)
        total_conversations = conv_result.scalar() or 0
        
        # Count messages
        msg_query = select(func.count(Message.id))
        msg_result = await self.session.execute(msg_query)
        total_messages = msg_result.scalar() or 0
        
        return {
            "total_conversations": total_conversations,
            "total_messages": total_messages,
        }
