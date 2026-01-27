import logging
import wikipedia
from mcp.server.fastmcp import FastMCP

# Import caching utilities
from cache import cache_result, get_cache_stats, clear_cache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

mcp = FastMCP("WikipediaSearch")


# =============================================================================
# Wikipedia Tools with Caching
# =============================================================================

@mcp.tool()
@cache_result("search", ttl=3600)  # Cache for 1 hour
def fetch_wikipedia_info(query: str) -> dict:
    """
    Search Wikipedia for a topic and return title, summary, and URL of the best match.
    
    Results are cached to reduce API calls and improve response time.
    """
    logger.info(f"Searching Wikipedia for: {query}")
    try:
        search_results = wikipedia.search(query)
        if not search_results:
            return {"error": "No results found for your query."}

        best_match = search_results[0]
        page = wikipedia.page(best_match)

        return {
            "title": page.title,
            "summary": page.summary,
            "url": page.url
        }

    except wikipedia.DisambiguationError as e:
        return {
            "error": f"Ambiguous topic. Try one of these: {', '.join(e.options[:5])}"
        }

    except wikipedia.PageError:
        return {
            "error": "No Wikipedia page could be loaded for this query."
        }


@mcp.tool()
@cache_result("sections", ttl=7200)  # Cache for 2 hours (sections change less often)
def list_wikipedia_sections(topic: str) -> dict:
    """
    Return a list of section titles from the Wikipedia page of a given topic.
    
    Results are cached for 2 hours.
    """
    try:
        page = wikipedia.page(topic)
        sections = page.sections
        return {"sections": sections}
    except Exception as e:
        return {"error": str(e)}

    
@mcp.tool()
@cache_result("content", ttl=7200)  # Cache for 2 hours
def get_section_content(topic: str, section_title: str) -> dict:
    """
    Return the content of a specific section in a Wikipedia article.
    
    Results are cached for 2 hours.
    """
    try:
        page = wikipedia.page(topic)
        content = page.section(section_title)
        if content:
            return {"content": content}
        else:
            return {"error": f"Section '{section_title}' not found in article '{topic}'."}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# Prompts (unchanged)
# =============================================================================

@mcp.prompt()
def highlight_sections_prompt(topic: str) -> str:
    """
    Identifies the most important sections from a Wikipedia article on the given topic.
    """
    return f"""
    The user is exploring the Wikipedia article on "{topic}".

    Given the list of section titles from the article, choose the 3–5 most important or interesting sections 
    that are likely to help someone learn about the topic.

    Return a bullet list of these section titles, along with 1-line explanations of why each one matters.
    """

@mcp.prompt()
def summarize_topic(topic: str) -> str:
    """Get a concise summary of any Wikipedia topic."""
    return f"Search Wikipedia for '{topic}' and provide a clear, concise summary with key facts."


@mcp.prompt()
def compare_topics(topic1: str, topic2: str) -> str:
    """Compare two Wikipedia topics side by side."""
    return f"Search Wikipedia for both '{topic1}' and '{topic2}', then provide a comparison highlighting their similarities and differences."


@mcp.prompt()
def deep_dive(topic: str, aspect: str) -> str:
    """Explore a specific aspect of a topic in depth."""
    return f"Search Wikipedia for '{topic}', find the section about '{aspect}', and explain it in detail."


# Run the MCP server
if __name__ == "__main__":
    logger.info("Starting MCP Wikipedia Server...")
    logger.info("📦 Caching enabled (Redis)")
    mcp.run(transport="stdio")