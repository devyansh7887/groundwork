import os
import re
import json
import logging
from collections import OrderedDict
from mcp.server.fastmcp import FastMCP
from pipeline import Pipeline

try:
    from qa_agent import QAAgent
except ImportError:
    class QAAgent:
        def index_repository(self, *args, **kwargs): pass
        async def answer_question(self, *args, **kwargs): return {"error": "QA Agent unavailable. Missing dependencies."}

# Configure logging to a file — do not pollute stdio (MCP uses stdio for protocol)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='mcp_server.log'
)
logger = logging.getLogger("mcp_server")

# Initialize MCP server
mcp = FastMCP("Groundwork")

# Global dependencies
pipeline = Pipeline()
qa_agent = QAAgent()

# Bounded LRU in-memory cache — prevents unbounded memory growth on long-running instances
_CACHE_MAX = 10
repo_cache: OrderedDict = OrderedDict()

_GITHUB_URL_RE = re.compile(r"^https://github\.com/[\w.\-]+/[\w.\-]+/?$")

def _validate_github_url(url: str) -> str:
    """Validates and normalises a GitHub repo URL. Raises ValueError on bad input."""
    url = url.strip().rstrip("/")
    if not _GITHUB_URL_RE.match(url):
        raise ValueError(
            f"Invalid GitHub repository URL: '{url}'. "
            "Expected format: https://github.com/owner/repo"
        )
    return url

def _cache_set(url: str, state: dict) -> None:
    """Insert/update cache with LRU eviction when the cap is exceeded."""
    if url in repo_cache:
        repo_cache.move_to_end(url)
    repo_cache[url] = state
    if len(repo_cache) > _CACHE_MAX:
        evicted = repo_cache.popitem(last=False)
        logger.info(f"MCP cache eviction: removed '{evicted[0]}'")


@mcp.tool()
async def analyze_repository(repo_url: str) -> str:
    """
    Runs the full Groundwork pipeline to analyze a public GitHub repository.
    Returns the architecture summary and the list of verified claims.

    Args:
        repo_url: Full GitHub repository URL (e.g. https://github.com/encode/starlette)
    """
    try:
        repo_url = _validate_github_url(repo_url)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    logger.info(f"Analyzing {repo_url}")
    try:
        final_state = await pipeline.run(repo_url)
        repo_name = final_state["repo_metadata"]["repo"]

        _cache_set(repo_url, final_state)

        # Index for Q&A
        qa_agent.index_repository(repo_name, final_state["downloaded_files"], final_state["readme_content"])

        result = {
            "architecture_summary": final_state["readme_content"],
            "claims": final_state["claims"],
            "sampled": final_state.get("repo_metadata", {}).get("sampled", False),
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.exception("Error during analysis")
        return json.dumps({"error": str(e)})


@mcp.tool()
async def ask_groundwork(repo_url: str, question: str) -> str:
    """
    Asks a grounded question about a previously analyzed repository.
    Returns the answer with Verified/Inferred/Unverified labels and file citations.

    Args:
        repo_url: The GitHub URL that was previously passed to analyze_repository.
        question: Natural language question about the repository architecture.
    """
    try:
        repo_url = _validate_github_url(repo_url)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    if repo_url not in repo_cache:
        return json.dumps({
            "error": f"Repository '{repo_url}' not analyzed yet. Call analyze_repository first."
        })

    state = repo_cache[repo_url]
    repo_cache.move_to_end(repo_url)  # mark as recently used
    repo_name = state["repo_metadata"]["repo"]

    try:
        res = await qa_agent.answer_question(repo_name, question, state["graph"], state["downloaded_files"])
        return json.dumps(res, indent=2)
    except Exception as e:
        logger.exception("Error during Q&A")
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    logger.info("Starting Groundwork MCP server")
    mcp.run(transport="stdio")
