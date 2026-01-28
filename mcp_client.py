"""
Wikipedia Search Agent - MCP Client with FastAPI
=================================================

This is the MAIN APPLICATION file that ties everything together.
It creates a FastAPI web server that:

1. Connects to the MCP Server (Wikipedia tools)
2. Uses LangGraph for AI agent orchestration
3. Persists conversations to PostgreSQL (Phase 2)
4. Caches results in Redis (Phase 1)

=== REQUEST FLOW ===

User Request → FastAPI → LangGraph Agent → MCP Tools → Wikipedia API
                 ↓                           ↓
             PostgreSQL               Redis Cache
          (save history)            (cache results)
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Annotated, List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing_extensions import TypedDict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import AnyMessage, add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import tools_condition, ToolNode

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.tools import load_mcp_tools


# =============================================================================
# Configuration
# =============================================================================

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

# LLM Provider Configuration
# Supported: "openai", "groq", "google", "ollama"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")

# Provider-specific settings
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GOOGLE_MODEL = os.environ.get("GOOGLE_MODEL", "gemini-1.5-flash")

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Use the same Python executable that's running this script
import sys
server_params = StdioServerParameters(
    command=sys.executable,
    args=[str(Path(__file__).parent / "mcp_server.py")]
)


def get_llm():
    """Get the configured LLM based on LLM_PROVIDER environment variable."""
    provider = LLM_PROVIDER.lower()
    
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        logger.info(f"Using OpenAI: {OPENAI_MODEL}")
        return ChatOpenAI(
            model=OPENAI_MODEL,
            temperature=0,
            openai_api_key=OPENAI_API_KEY
        ), OPENAI_MODEL
    
    elif provider == "groq":
        from langchain_groq import ChatGroq
        logger.info(f"Using Groq: {GROQ_MODEL}")
        return ChatGroq(
            model=GROQ_MODEL,
            temperature=0,
            groq_api_key=GROQ_API_KEY
        ), GROQ_MODEL
    
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        logger.info(f"Using Google: {GOOGLE_MODEL}")
        return ChatGoogleGenerativeAI(
            model=GOOGLE_MODEL,
            temperature=0,
            google_api_key=GOOGLE_API_KEY
        ), GOOGLE_MODEL
    
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        logger.info(f"Using Ollama: {OLLAMA_MODEL}")
        return ChatOllama(
            model=OLLAMA_MODEL,
            temperature=0,
            base_url=OLLAMA_BASE_URL
        ), OLLAMA_MODEL
    
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}. Use: openai, groq, google, ollama")


# =============================================================================
# LangGraph State & Agent
# =============================================================================

class State(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]


# Store the current model name for health check
_current_model = None


async def create_graph(session):
    """Create and compile the LangGraph agent with MCP tools."""
    global _current_model
    tools = await load_mcp_tools(session)

    llm, _current_model = get_llm()
    llm_with_tools = llm.bind_tools(tools)

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", """You are a fast Wikipedia assistant. Rules:
1. Use tools immediately - don't explain what you'll do first
2. Give concise answers (2-3 paragraphs max)
3. Always include the Wikipedia URL
4. Use only ONE tool call when possible"""),
        MessagesPlaceholder("messages")
    ])

    chat_llm = prompt_template | llm_with_tools

    def chat_node(state: State) -> State:
        state["messages"] = chat_llm.invoke({"messages": state["messages"]})
        return state

    graph = StateGraph(State)
    graph.add_node("chat_node", chat_node)
    graph.add_node("tool_node", ToolNode(tools=tools))
    graph.add_edge(START, "chat_node")
    graph.add_conditional_edges("chat_node", tools_condition, {
        "tools": "tool_node",
        "__end__": END
    })
    graph.add_edge("tool_node", "chat_node")

    return graph.compile(checkpointer=MemorySaver())


# =============================================================================
# Web Server Lifecycle
# =============================================================================

_agent = None
_mcp_session = None
_mcp_context = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle - startup and shutdown.
    
    === WHAT HAPPENS ON STARTUP ===
    1. Connect to MCP server (Wikipedia tools)
    2. Create LangGraph agent
    3. Initialize database (Phase 2) - if available
    
    === WHAT HAPPENS ON SHUTDOWN ===
    1. Close database connections
    2. Close MCP connection
    """
    global _agent, _mcp_session, _mcp_context

    # === STARTUP ===
    
    # Initialize MCP connection (Wikipedia tools)
    logger.info("Starting MCP connection...")
    _mcp_context = stdio_client(server_params)
    read, write = await _mcp_context.__aenter__()
    _mcp_session = ClientSession(read, write)
    await _mcp_session.__aenter__()
    await _mcp_session.initialize()

    # Create the LangGraph agent
    _agent = await create_graph(_mcp_session)
    logger.info(f"✅ Wikipedia MCP agent ready! Provider: {LLM_PROVIDER} | Model: {_current_model}")

    # Initialize database (Phase 2)
    # GRACEFUL DEGRADATION: App works even if database is unavailable
    try:
        from database import init_database
        await init_database()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.warning(f"⚠️ Database not available: {e}. Conversation history disabled.")

    yield  # App runs here

    # === SHUTDOWN ===
    logger.info("Shutting down...")
    
    # Close database connections
    try:
        from database import close_database
        await close_database()
    except Exception:
        pass  # Ignore errors during shutdown
    
    # Close MCP connection
    await _mcp_session.__aexit__(None, None, None)
    await _mcp_context.__aexit__(None, None, None)


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Wikipedia Search Agent",
    description="AI-powered Wikipedia search using MCP",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# =============================================================================
# Request/Response Models (Pydantic)
# =============================================================================

class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


class ChatResponse(BaseModel):
    response: str


class PromptArgument(BaseModel):
    name: str
    description: Optional[str] = None
    required: bool = True


class PromptInfo(BaseModel):
    name: str
    description: Optional[str] = None
    arguments: List[PromptArgument]


class PromptsResponse(BaseModel):
    prompts: List[PromptInfo]


class ExecutePromptRequest(BaseModel):
    prompt_name: str
    arguments: dict
    thread_id: str = "default"


class HealthResponse(BaseModel):
    status: str
    model: str


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for monitoring."""
    return HealthResponse(status="healthy", model=_current_model or "loading...")


# =============================================================================
# Cache Endpoints (Phase 1: Redis)
# =============================================================================

@app.get("/api/cache/stats")
async def cache_stats():
    """
    Get Redis cache statistics for monitoring.
    
    Returns:
        - cached_keys: Number of items in cache
        - memory_usage: Redis memory usage
        - cache_ttl: Default TTL setting
    """
    from cache import get_cache_stats
    return get_cache_stats()


@app.delete("/api/cache")
async def clear_cache():
    """
    Clear all cached Wikipedia data.
    
    Use this when you want fresh data from Wikipedia.
    """
    from cache import clear_cache as do_clear
    deleted = do_clear()
    return {"cleared": deleted, "message": f"Cleared {deleted} cached items"}


# =============================================================================
# Database Endpoints (Phase 2: PostgreSQL)
# =============================================================================

@app.get("/api/db/stats")
async def database_stats():
    """
    Get database statistics.
    
    Returns:
        - status: connected/disconnected
        - total_conversations: Number of saved conversations
        - total_messages: Number of saved messages
    """
    try:
        from database import get_session
        from repository import ConversationRepository
        
        async with get_session() as session:
            repo = ConversationRepository(session)
            stats = await repo.get_conversation_stats()
            stats["status"] = "connected"
            return stats
    except Exception as e:
        return {"status": "disconnected", "error": str(e)}


@app.get("/api/conversations")
async def list_conversations(limit: int = 20, offset: int = 0):
    """
    List saved conversations with pagination.
    
    Args:
        limit: Maximum conversations to return (default: 20)
        offset: Skip this many for pagination (default: 0)
    """
    try:
        from database import get_session
        from repository import ConversationRepository
        
        async with get_session() as session:
            repo = ConversationRepository(session)
            conversations = await repo.list_conversations(limit=limit, offset=offset)
            return {
                "conversations": [
                    {
                        "thread_id": c.thread_id,
                        "title": c.title,
                        "created_at": c.created_at.isoformat(),
                        "updated_at": c.updated_at.isoformat(),
                    }
                    for c in conversations
                ]
            }
    except Exception as e:
        return {"error": str(e), "conversations": []}


@app.get("/api/conversations/{thread_id}/messages")
async def get_conversation_messages(thread_id: str, limit: int = 50):
    """
    Get messages from a specific conversation.
    
    Args:
        thread_id: The conversation identifier
        limit: Maximum messages to return (default: 50)
    """
    try:
        from database import get_session
        from repository import ConversationRepository
        
        async with get_session() as session:
            repo = ConversationRepository(session)
            messages = await repo.get_conversation_history(thread_id, limit=limit)
            return {
                "thread_id": thread_id,
                "messages": [
                    {
                        "role": m.role.value,
                        "content": m.content,
                        "created_at": m.created_at.isoformat(),
                    }
                    for m in messages
                ]
            }
    except Exception as e:
        return {"error": str(e), "messages": []}


# =============================================================================
# Chat Endpoint (Core Functionality)
# =============================================================================

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint - handles user messages.
    
    Flow:
    1. Receive user message
    2. Invoke LangGraph agent (uses MCP tools to search Wikipedia)
    3. Save conversation to database (Phase 2)
    4. Return AI response
    
    === GRACEFUL DEGRADATION ===
    If the database is unavailable, chat still works - we just don't save history.
    """
    if not _agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        logger.debug(f"Chat request: {request.message[:50]}...")
        
        # Invoke the LangGraph agent
        result = await _agent.ainvoke(
            {"messages": request.message},
            config={"configurable": {"thread_id": request.thread_id}}
        )
        response_content = result["messages"][-1].content
        
        # === PHASE 2: Save to Database ===
        # Wrapped in try/except for graceful degradation
        try:
            from database import get_session
            from repository import ConversationRepository
            from models import MessageRole
            
            async with get_session() as session:
                repo = ConversationRepository(session)
                # Save both the user message and AI response
                await repo.add_message(request.thread_id, MessageRole.USER, request.message)
                await repo.add_message(request.thread_id, MessageRole.ASSISTANT, response_content)
        except Exception as db_error:
            # Log but don't fail - chat still works without DB
            logger.debug(f"Database save skipped: {db_error}")
        
        return ChatResponse(response=response_content)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# MCP Prompts Endpoints
# =============================================================================

@app.get("/api/prompts", response_model=PromptsResponse)
async def get_prompts():
    """Get available MCP prompts."""
    if not _mcp_session:
        raise HTTPException(status_code=503, detail="MCP session not initialized")

    try:
        prompt_response = await _mcp_session.list_prompts()

        if not prompt_response or not prompt_response.prompts:
            return PromptsResponse(prompts=[])

        prompts = []
        for p in prompt_response.prompts:
            args = []
            if p.arguments:
                for arg in p.arguments:
                    args.append(PromptArgument(
                        name=arg.name,
                        description=getattr(arg, 'description', None),
                        required=getattr(arg, 'required', True)
                    ))
            prompts.append(PromptInfo(
                name=p.name,
                description=getattr(p, 'description', None),
                arguments=args
            ))

        return PromptsResponse(prompts=prompts)
    except Exception as e:
        logger.error(f"Prompts error: {e}")
        return PromptsResponse(prompts=[])


@app.post("/api/prompts/execute", response_model=ChatResponse)
async def execute_prompt(request: ExecutePromptRequest):
    """Execute an MCP prompt and return the result."""
    if not _agent or not _mcp_session:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        response = await _mcp_session.get_prompt(request.prompt_name, request.arguments)
        prompt_text = response.messages[0].content.text

        result = await _agent.ainvoke(
            {"messages": [HumanMessage(content=prompt_text)]},
            config={"configurable": {"thread_id": request.thread_id}}
        )
        return ChatResponse(response=result["messages"][-1].content)
    except Exception as e:
        logger.error(f"Prompt execution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Static Files & UI
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the chat UI."""
    static_path = Path(__file__).parent / "static" / "index.html"
    return static_path.read_text()


app.mount("/static", StaticFiles(directory="static"), name="static")


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Wikipedia Search Agent on {HOST}:{PORT}")
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        access_log=True,
        log_level="info"
    )
