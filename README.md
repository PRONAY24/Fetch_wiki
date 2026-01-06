# 🔍 Wikipedia Search Agent

An intelligent Wikipedia search agent built with **Model Context Protocol (MCP)**, **LangGraph**, and **LangChain**. This project provides both a powerful MCP server with Wikipedia tools and a beautiful web interface for interactive searches.

## ✨ Features

- **MCP Wikipedia Server** - Exposes Wikipedia functionality as MCP tools
- **LangGraph Agent** - Orchestrates tool calls with a stateful conversation agent
- **Interactive Web UI** - Modern chat interface with prompt templates
- **Multiple Search Modes**:
  - 📖 Topic summaries with key facts
  - 📑 Section exploration and deep dives
  - ⚖️ Side-by-side topic comparisons

## 🛠️ MCP Tools Available

| Tool | Description |
|------|-------------|
| `fetch_wikipedia_info` | Search Wikipedia and get title, summary, and URL |
| `list_wikipedia_sections` | Get all section titles from a Wikipedia article |
| `get_section_content` | Retrieve content of a specific section |

## 🎯 Built-in Prompts

- **Summarize Topic** - Get a concise summary of any Wikipedia topic
- **Compare Topics** - Compare two topics side by side
- **Deep Dive** - Explore a specific aspect of a topic in depth
- **Highlight Sections** - Identify the most important sections of an article

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- OpenAI API Key

### Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/wikipedia-search-agent.git
cd wikipedia-search-agent

# Install dependencies
pip install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY="your-api-key-here"
```

### Running the Application

```bash
# Start the web server
python mcp_client.py
```

Then open your browser to `http://localhost:8000`

### Using as MCP Server Only

You can also use the MCP server standalone:

```bash
python mcp_server.py
```

## 📁 Project Structure

```
├── mcp_server.py      # MCP server with Wikipedia tools
├── mcp_client.py      # FastAPI web server + LangGraph agent
├── static/
│   └── index.html     # Chat web interface
├── docs/
│   ├── ARCHITECTURE.md  # How the application works
│   └── DEPLOYMENT.md    # Production deployment guide
├── requirements.txt   # Python dependencies
└── README.md
```

## 📚 Documentation

- **[Architecture Guide](docs/ARCHITECTURE.md)** - Understand how the application works, components, and data flow
- **[Deployment Guide](docs/DEPLOYMENT.md)** - Step-by-step production deployment on Linux servers

## 🔧 Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | - | Your OpenAI API key (required) |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model to use |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8000` | Server port |
| `LOG_LEVEL` | `INFO` | Logging level |

## 🏗️ Tech Stack

- **[MCP (Model Context Protocol)](https://modelcontextprotocol.io/)** - Tool & prompt management
- **[LangGraph](https://langchain-ai.github.io/langgraph/)** - Stateful agent orchestration
- **[LangChain](https://python.langchain.com/)** - LLM integration
- **[FastAPI](https://fastapi.tiangolo.com/)** - Web framework
- **[Wikipedia-API](https://pypi.org/project/wikipedia/)** - Wikipedia data access

## 📝 License

MIT License

## 🤝 Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

---

Built with ❤️ using MCP and LangGraph
