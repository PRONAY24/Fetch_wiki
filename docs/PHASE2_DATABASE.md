# 📦 Phase 2: PostgreSQL Database - Learning Guide

This guide explains the database persistence concepts implemented in your Wikipedia Agent.

---

## 🎯 Overview: What We Built

```
                    ┌─────────────────────────────────────────┐
                    │           Wikipedia Agent               │
                    ├─────────────────────────────────────────┤
User Message ──────►│  FastAPI  ────►  LangGraph Agent       │
                    │     │                    │               │
                    │     ▼                    ▼               │
                    │ PostgreSQL          MCP Tools           │
                    │ (save history)    (search Wikipedia)    │
                    └─────────────────────────────────────────┘
```

**Phase 2 adds**: Persistent storage of conversation history in PostgreSQL.

---

## 🧠 Key Concepts Explained

### 1. ORM (Object-Relational Mapping)

**Problem**: Writing SQL is tedious and error-prone.

```sql
-- Raw SQL - hard to maintain
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    thread_id VARCHAR(100) UNIQUE,
    title VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO conversations (thread_id, title) VALUES ('session-123', 'About Python');
SELECT * FROM conversations WHERE thread_id = 'session-123';
```

**Solution**: Write Python classes, ORM generates SQL.

```python
# Python class - easy to read and maintain
class Conversation(Base):
    __tablename__ = "conversations"
    id = mapped_column(Integer, primary_key=True)
    thread_id = mapped_column(String(100), unique=True)
    title = mapped_column(String(255))
    created_at = mapped_column(DateTime, default=datetime.utcnow)

# Usage is intuitive
conversation = Conversation(thread_id="session-123", title="About Python")
session.add(conversation)  # SQLAlchemy generates INSERT automatically!
```

---

### 2. Connection Pooling

**Problem**: Opening database connections is SLOW (50-100ms each).

```
Without pooling (slow):
Request 1: [Connect 50ms] → Query → Disconnect
Request 2: [Connect 50ms] → Query → Disconnect
Request 3: [Connect 50ms] → Query → Disconnect
Total connection overhead: 150ms
```

**Solution**: Create connections once, reuse them.

```
With pooling (fast):
Startup: Create pool of 5 connections
Request 1: Borrow → Query → Return (2ms)
Request 2: Borrow → Query → Return (2ms)
Request 3: Borrow → Query → Return (2ms)
Total connection overhead: 6ms (25x faster!)
```

**Our code** (in `database.py`):
```python
_engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,         # Keep 5 connections ready
    max_overflow=10,     # Allow 10 more during peak
)
```

---

### 3. Async Database Operations

**Problem**: Blocking database calls freeze the server.

```
Synchronous (blocking):
Request 1 arrives → DB query (100ms) → Server waits, can't handle other requests
Request 2 arrives → Must wait for Request 1 to finish!
```

**Solution**: Async allows concurrent handling.

```
Asynchronous (non-blocking):
Request 1 arrives → Start DB query → Handle Request 2 while waiting
Request 2 arrives → Start processing → Handle Request 3 while waiting
All requests processed in parallel!
```

**Our code**:
```python
# Async function (returns immediately, result comes later)
result = await session.execute(query)  # Server can do other work while waiting
```

---

### 4. Repository Pattern

**Problem**: Business logic mixed with database queries = hard to test/maintain.

```python
# Bad: Everything mixed together
@app.post("/api/chat")
async def chat(request):
    # Business logic + SQL = messy
    query = text("SELECT * FROM conversations WHERE thread_id = :id")
    result = await session.execute(query, {"id": request.thread_id})
    if not result:
        await session.execute(
            text("INSERT INTO conversations (thread_id) VALUES (:id)"),
            {"id": request.thread_id}
        )
    # More mixed code...
```

**Solution**: Separate data access into a repository.

```python
# Good: Clean separation
@app.post("/api/chat")
async def chat(request):
    repo = ConversationRepository(session)
    conversation = await repo.get_or_create_conversation(request.thread_id)
    await repo.add_message(request.thread_id, MessageRole.USER, request.message)
```

---

### 5. Graceful Degradation

**Problem**: If database fails, entire app crashes.

**Solution**: Wrap database calls in try/except, continue without DB.

```python
# In mcp_client.py
try:
    # Try to save to database
    async with get_session() as session:
        repo = ConversationRepository(session)
        await repo.add_message(thread_id, MessageRole.USER, message)
except Exception as db_error:
    # Database unavailable? Log and continue
    logger.debug(f"Database save skipped: {db_error}")
    # Chat still works! Just no history.
```

---

## 📁 Files Created

| File | Purpose | Key Concept |
|------|---------|-------------|
| `models.py` | Define database tables | ORM |
| `database.py` | Manage connections | Connection Pooling |
| `repository.py` | CRUD operations | Repository Pattern |

---

## 🗃️ Database Schema

```
┌─────────────────────────────────────────────────────────────┐
│                     CONVERSATIONS                            │
├──────────────┬────────────────────┬──────────────────────────┤
│ id (PK)      │ INTEGER            │ Auto-increment           │
│ thread_id    │ VARCHAR(100)       │ UNIQUE, INDEXED          │
│ title        │ VARCHAR(255)       │ Auto-set from 1st msg    │
│ created_at   │ TIMESTAMP          │ When created             │
│ updated_at   │ TIMESTAMP          │ Last activity            │
└──────────────┴────────────────────┴──────────────────────────┘
                           │
                           │ ONE-TO-MANY
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                        MESSAGES                              │
├──────────────┬────────────────────┬──────────────────────────┤
│ id (PK)      │ INTEGER            │ Auto-increment           │
│ conv_id (FK) │ INTEGER            │ Links to conversation    │
│ role         │ ENUM               │ user/assistant/system    │
│ content      │ TEXT               │ Message content          │
│ created_at   │ TIMESTAMP          │ When sent                │
│ tokens_used  │ INTEGER            │ For cost tracking        │
└──────────────┴────────────────────┴──────────────────────────┘
```

---

## 🔧 Setup on Your Linode VM

### 1. Install PostgreSQL

```bash
# Install
sudo apt update
sudo apt install postgresql postgresql-contrib

# Start and enable
sudo systemctl enable postgresql
sudo systemctl start postgresql
```

### 2. Create Database and User

```bash
# Switch to postgres user
sudo -u postgres psql

# In PostgreSQL shell:
CREATE DATABASE wikipedia_agent;
CREATE USER appuser WITH PASSWORD '3M23nhgh';
GRANT ALL PRIVILEGES ON DATABASE wikipedia_agent TO appuser;
\q
```

### 3. Update .env

```bash
# Add to your .env file
DATABASE_URL=postgresql+asyncpg://appuser:3M23nhgh@localhost:5432/wikipedia_agent
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
```

### 4. Install Python Dependencies

```bash
pip install sqlalchemy[asyncio] asyncpg alembic
```

### 5. Restart Application

```bash
sudo systemctl restart wikipedia-agent
```

---

## 📊 New API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/db/stats` | GET | Get conversation/message counts |
| `/api/conversations` | GET | List saved conversations |
| `/api/conversations/{id}/messages` | GET | Get conversation history |

---

## 🧪 Test Commands

```bash
# Check database status
curl http://localhost:8000/api/db/stats

# List conversations
curl http://localhost:8000/api/conversations

# Get specific conversation
curl http://localhost:8000/api/conversations/session-123/messages

# Chat (will save to database)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me about Python", "thread_id": "test-1"}'

# Check if it was saved
curl http://localhost:8000/api/conversations
```

---

## ✅ What You Learned

- [x] **ORM**: Map Python classes to database tables
- [x] **Connection Pooling**: Reuse connections for speed
- [x] **Async/Await**: Non-blocking database operations
- [x] **Repository Pattern**: Clean separation of concerns
- [x] **Graceful Degradation**: App works even if DB is down

---

## ⏭️ Next: Phase 3 - Message Queues

Coming up: Async processing with Redis queues!
