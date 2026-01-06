# 🏗️ Application Architecture - Wikipedia Search Agent

This document explains how the Wikipedia Search Agent works, its components, and the flow of data through the system.

---

## Table of Contents

1. [Overview](#overview)
2. [Technology Stack](#technology-stack)
3. [System Architecture](#system-architecture)
4. [Component Deep Dive](#component-deep-dive)
5. [Request Flow](#request-flow)
6. [MCP Protocol Explained](#mcp-protocol-explained)
7. [LangGraph Agent](#langgraph-agent)
8. [API Endpoints](#api-endpoints)
9. [Frontend](#frontend)

---

## Overview

The Wikipedia Search Agent is an AI-powered application that allows users to search, summarize, and explore Wikipedia articles through a conversational interface.

**Key Features:**
- 🔍 Search Wikipedia topics
- 📖 Get article summaries
- 📑 Explore article sections
- ⚖️ Compare two topics
- 🎯 Deep dive into specific aspects

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Frontend** | HTML/CSS/JavaScript | Chat interface |
| **API Server** | FastAPI + Uvicorn | HTTP server, REST endpoints |
| **AI Agent** | LangGraph | Orchestrates tool calls |
| **LLM** | OpenAI (GPT-5-nano) | Natural language understanding |
| **Tool Server** | MCP (Model Context Protocol) | Wikipedia tools |
| **Data Source** | Wikipedia API | Article data |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USER BROWSER                                │
│                          http://your-server.com                          │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                               NGINX                                      │
│                         (Reverse Proxy :80)                              │
│   • SSL termination  • Static files  • Load balancing                   │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           MCP CLIENT                                     │
│                    (mcp_client.py - FastAPI :8000)                       │
│                                                                          │
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────────────────┐  │
│  │   FastAPI   │    │    LangGraph    │    │     MCP Client          │  │
│  │   Server    │───▶│     Agent       │───▶│    (Tool Loader)        │  │
│  │             │    │                 │    │                         │  │
│  │ • /api/chat │    │ • State machine │    │ • Connects to MCP       │  │
│  │ • /api/...  │    │ • Tool routing  │    │   server via stdio      │  │
│  │ • /health   │    │ • Memory        │    │ • Loads tools           │  │
│  └─────────────┘    └─────────────────┘    └───────────┬─────────────┘  │
└────────────────────────────────────────────────────────┼────────────────┘
                                                         │
                            ┌────────────────────────────┘
                            │ stdio (subprocess)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           MCP SERVER                                     │
│                        (mcp_server.py)                                   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                         MCP Tools                                │    │
│  │                                                                  │    │
│  │  fetch_wikipedia_info()    - Search and get article summary     │    │
│  │  list_wikipedia_sections() - Get section titles                 │    │
│  │  get_section_content()     - Get specific section text          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                        MCP Prompts                               │    │
│  │                                                                  │    │
│  │  summarize_topic()         - Concise summary prompt             │    │
│  │  compare_topics()          - Side-by-side comparison            │    │
│  │  deep_dive()               - Explore specific aspect            │    │
│  │  highlight_sections()      - Find important sections            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────┬────────────────┘
                                                         │
                                                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                                │
│                                                                          │
│  ┌─────────────────────┐         ┌─────────────────────────────────┐    │
│  │    Wikipedia API    │         │         OpenAI API              │    │
│  │                     │         │                                 │    │
│  │  • Search articles  │         │  • GPT-5-nano model             │    │
│  │  • Get content      │         │  • Natural language processing  │    │
│  │  • Get sections     │         │  • Tool call decisions          │    │
│  └─────────────────────┘         └─────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Deep Dive

### 1. MCP Server (`mcp_server.py`)

The MCP (Model Context Protocol) server exposes Wikipedia functionality as **tools** that an AI agent can use.

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("WikipediaSearch")

@mcp.tool()
def fetch_wikipedia_info(query: str) -> dict:
    """Search Wikipedia and return title, summary, URL."""
    # ...
```

**What is MCP?**

MCP is a protocol developed by Anthropic that standardizes how AI models interact with external tools and data sources.

```
┌─────────────┐                    ┌─────────────┐
│  AI Model   │◀──── MCP ────────▶│   Tools     │
│  (Client)   │   (standard API)   │  (Server)   │
└─────────────┘                    └─────────────┘
```

**MCP Tools defined:**

| Tool | Purpose | Parameters |
|------|---------|------------|
| `fetch_wikipedia_info` | Get article summary | `query: str` |
| `list_wikipedia_sections` | Get section titles | `topic: str` |
| `get_section_content` | Get section text | `topic: str, section_title: str` |

**MCP Prompts defined:**

Prompts are pre-defined templates for common tasks:

| Prompt | Purpose | Parameters |
|--------|---------|------------|
| `summarize_topic` | Quick summary | `topic: str` |
| `compare_topics` | Compare two things | `topic1: str, topic2: str` |
| `deep_dive` | Explore aspect | `topic: str, aspect: str` |
| `highlight_sections` | Find key sections | `topic: str` |

### 2. MCP Client (`mcp_client.py`)

The client does three things:
1. **Runs a FastAPI web server** for the UI
2. **Connects to MCP server** to load tools
3. **Runs a LangGraph agent** for AI orchestration

#### FastAPI Server

```python
app = FastAPI(
    title="Wikipedia Search Agent",
    lifespan=lifespan  # Manages MCP connection lifecycle
)
```

#### MCP Connection

```python
# Start MCP server as subprocess
server_params = StdioServerParameters(
    command=sys.executable,  # Python interpreter
    args=["mcp_server.py"]   # Server script
)

# Connect and load tools
async with stdio_client(server_params) as (read, write):
    session = ClientSession(read, write)
    tools = await load_mcp_tools(session)
```

The client spawns the MCP server as a **subprocess** and communicates via **stdio** (standard input/output).

### 3. LangGraph Agent

LangGraph is a framework for building stateful, multi-step AI agents.

```python
# Define the state
class State(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]

# Build the graph
graph = StateGraph(State)
graph.add_node("chat_node", chat_node)      # LLM thinking
graph.add_node("tool_node", ToolNode(tools)) # Tool execution
graph.add_edge(START, "chat_node")
graph.add_conditional_edges("chat_node", tools_condition, {
    "tools": "tool_node",
    "__end__": END
})
graph.add_edge("tool_node", "chat_node")
```

**Visual representation:**

```
                    ┌─────────────────┐
                    │      START      │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
              ┌────▶│   chat_node     │◀────┐
              │     │  (LLM thinks)   │     │
              │     └────────┬────────┘     │
              │              │              │
              │     ┌────────┴────────┐     │
              │     │ tools_condition │     │
              │     │ (need tools?)   │     │
              │     └────────┬────────┘     │
              │              │              │
              │     ┌────────┴────────┐     │
              │     │                 │     │
              │   [yes]             [no]    │
              │     │                 │     │
              │     ▼                 ▼     │
              │ ┌─────────┐    ┌─────────┐  │
              │ │tool_node│    │   END   │  │
              │ │(execute)│    └─────────┘  │
              │ └────┬────┘                 │
              │      │                      │
              └──────┘                      │
                (loop back)
```

---

## Request Flow

Let's trace a complete request: **"Tell me about Python programming"**

### Step 1: User Sends Message

```
Browser → POST /api/chat
{
  "message": "Tell me about Python programming",
  "thread_id": "user-123"
}
```

### Step 2: FastAPI Receives Request

```python
@app.post("/api/chat")
async def chat(request: ChatRequest):
    result = await _agent.ainvoke(
        {"messages": request.message},
        config={"configurable": {"thread_id": request.thread_id}}
    )
```

### Step 3: LangGraph Agent Processes

```
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph Execution                          │
│                                                                 │
│  Step 1: chat_node                                              │
│  ├─ Send to OpenAI: "Tell me about Python programming"         │
│  ├─ LLM decides: I need to use fetch_wikipedia_info tool       │
│  └─ Returns: ToolCall(name="fetch_wikipedia_info",             │
│                       args={"query": "Python programming"})     │
│                                                                 │
│  Step 2: tool_node                                              │
│  ├─ Execute: fetch_wikipedia_info("Python programming")        │
│  ├─ MCP Server queries Wikipedia API                           │
│  └─ Returns: {title, summary, url}                             │
│                                                                 │
│  Step 3: chat_node (again)                                      │
│  ├─ Send to OpenAI: [user message + tool result]               │
│  ├─ LLM formats the response                                   │
│  └─ Returns: "Python is a high-level programming..."           │
│                                                                 │
│  Step 4: END                                                    │
│  └─ No more tool calls needed                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Step 4: Response Returned

```json
{
  "response": "Python is a high-level, general-purpose programming language..."
}
```

### Complete Sequence Diagram

```
┌──────┐    ┌────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐
│Browser│   │FastAPI │    │LangGraph │    │  OpenAI  │    │MCP Server│    │Wikipedia│
└──┬───┘    └───┬────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬────┘
   │            │              │               │               │               │
   │ POST /chat │              │               │               │               │
   │───────────▶│              │               │               │               │
   │            │ invoke agent │               │               │               │
   │            │─────────────▶│               │               │               │
   │            │              │ chat request  │               │               │
   │            │              │──────────────▶│               │               │
   │            │              │               │               │               │
   │            │              │ tool_call     │               │               │
   │            │              │◀──────────────│               │               │
   │            │              │               │               │               │
   │            │              │ execute tool  │               │               │
   │            │              │──────────────────────────────▶│               │
   │            │              │               │               │ search        │
   │            │              │               │               │──────────────▶│
   │            │              │               │               │               │
   │            │              │               │               │ article data  │
   │            │              │               │               │◀──────────────│
   │            │              │ tool result   │               │               │
   │            │              │◀──────────────────────────────│               │
   │            │              │               │               │               │
   │            │              │ format response               │               │
   │            │              │──────────────▶│               │               │
   │            │              │               │               │               │
   │            │              │ final text    │               │               │
   │            │              │◀──────────────│               │               │
   │            │ response     │               │               │               │
   │            │◀─────────────│               │               │               │
   │ JSON       │              │               │               │               │
   │◀───────────│              │               │               │               │
   │            │              │               │               │               │
```

---

## MCP Protocol Explained

### What is MCP?

**Model Context Protocol (MCP)** is an open standard for connecting AI models to external tools and data sources.

### Why MCP?

Before MCP, every AI integration was custom:
```
┌─────────┐     custom code      ┌─────────┐
│   AI    │◀────────────────────▶│ Tool 1  │
└─────────┘     custom code      ├─────────┤
      ▲        ─────────────────▶│ Tool 2  │
      │         custom code      ├─────────┤
      └────────────────────────▶│ Tool 3  │
                                 └─────────┘
```

With MCP, one standard protocol:
```
┌─────────┐                      ┌─────────┐
│   AI    │◀───── MCP ─────────▶│ Tool 1  │
└─────────┘      (standard)      ├─────────┤
      ▲          ───────────────▶│ Tool 2  │
      │          ───────────────▶│ Tool 3  │
      └─────────────────────────▶│ Tool N  │
                                 └─────────┘
```

### MCP Concepts

| Concept | Description |
|---------|-------------|
| **Server** | Exposes tools, prompts, resources |
| **Client** | Connects to server, invokes tools |
| **Tool** | Function the AI can call |
| **Prompt** | Pre-defined template for common tasks |
| **Resource** | Data the AI can read |
| **Transport** | How client/server communicate (stdio, SSE, etc.) |

### Our MCP Setup

```python
# Server (mcp_server.py)
mcp = FastMCP("WikipediaSearch")

@mcp.tool()
def fetch_wikipedia_info(query: str) -> dict:
    """Tool description shown to the AI."""
    return wikipedia.page(query)

# Client (mcp_client.py)
server_params = StdioServerParameters(
    command=sys.executable,
    args=["mcp_server.py"]
)

# Connect via stdio (subprocess pipes)
async with stdio_client(server_params) as (read, write):
    session = ClientSession(read, write)
    tools = await load_mcp_tools(session)
```

---

## API Endpoints

### Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "model": "gpt-5-nano"
}
```

### Chat

```http
POST /api/chat
Content-Type: application/json

{
  "message": "Tell me about Python",
  "thread_id": "optional-session-id"
}
```

**Response:**
```json
{
  "response": "Python is a high-level programming language..."
}
```

### List Prompts

```http
GET /api/prompts
```

**Response:**
```json
{
  "prompts": [
    {
      "name": "summarize_topic",
      "description": "Get a concise summary of any Wikipedia topic",
      "arguments": [
        {"name": "topic", "required": true}
      ]
    }
  ]
}
```

### Execute Prompt

```http
POST /api/prompts/execute
Content-Type: application/json

{
  "prompt_name": "compare_topics",
  "arguments": {
    "topic1": "Python",
    "topic2": "JavaScript"
  },
  "thread_id": "optional-session-id"
}
```

---

## Frontend

The frontend is a single HTML file (`static/index.html`) with embedded CSS and JavaScript.

### Features

- 💬 Chat interface with message bubbles
- 📝 Pre-defined prompt templates
- 🔄 Loading indicators
- 📱 Responsive design

### Structure

```html
<!-- Chat container -->
<div class="chat-container">
  <div class="chat-header">...</div>
  <div class="chat-messages">...</div>
  <div class="prompt-panel">...</div>
  <div class="chat-input">...</div>
</div>
```

### JavaScript Flow

```javascript
// Send message
async function sendMessage() {
  const message = inputEl.value;
  addMessage(message, 'user');
  
  const response = await fetch('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ message })
  });
  
  const data = await response.json();
  addMessage(data.response, 'assistant');
}
```

---

## Summary

### How Everything Connects

1. **User** types message in browser
2. **Nginx** proxies request to FastAPI
3. **FastAPI** passes to LangGraph agent
4. **LangGraph** sends to OpenAI for decision
5. **OpenAI** decides to call a tool
6. **LangGraph** executes tool via MCP
7. **MCP Server** calls Wikipedia API
8. **Response** flows back through the chain
9. **User** sees formatted answer

### Key Takeaways

- **MCP** standardizes tool integration
- **LangGraph** handles multi-step reasoning
- **FastAPI** provides the web interface
- **Nginx** handles production concerns (SSL, proxying)
- **Systemd** keeps everything running

---

## Further Reading

- [MCP Documentation](https://modelcontextprotocol.io/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [OpenAI API Reference](https://platform.openai.com/docs)
