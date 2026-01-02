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

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.tools import load_mcp_tools


# =============================================================================
# Configuration
# =============================================================================

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

server_params = StdioServerParameters(
    command="python",
    args=["mcp_server.py"]
)


# =============================================================================
# LangGraph State & Agent
# =============================================================================

class State(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]


async def create_graph(session):
    """Create and compile the LangGraph agent with MCP tools."""
    tools = await load_mcp_tools(session)

    llm = ChatOpenAI(
        model=OPENAI_MODEL,
        temperature=0,
        openai_api_key=OPENAI_API_KEY
    )
    llm_with_tools = llm.bind_tools(tools)

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant that uses tools to search Wikipedia. Be concise and informative."),
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
# Web Server
# =============================================================================

_agent = None
_mcp_session = None
_mcp_context = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage MCP connection lifecycle."""
    global _agent, _mcp_session, _mcp_context

    logger.info("Starting MCP connection...")

    _mcp_context = stdio_client(server_params)
    read, write = await _mcp_context.__aenter__()
    _mcp_session = ClientSession(read, write)
    await _mcp_session.__aenter__()
    await _mcp_session.initialize()

    _agent = await create_graph(_mcp_session)
    logger.info(f"✅ Wikipedia MCP agent ready! Model: {OPENAI_MODEL}")

    yield

    logger.info("Shutting down MCP connection...")
    await _mcp_session.__aexit__(None, None, None)
    await _mcp_context.__aexit__(None, None, None)


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
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# =============================================================================
# Request/Response Models
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
    """Health check endpoint."""
    return HealthResponse(status="healthy", model=OPENAI_MODEL)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle regular chat messages."""
    if not _agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        logger.debug(f"Chat request: {request.message[:50]}...")
        result = await _agent.ainvoke(
            {"messages": request.message},
            config={"configurable": {"thread_id": request.thread_id}}
        )
        return ChatResponse(response=result["messages"][-1].content)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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