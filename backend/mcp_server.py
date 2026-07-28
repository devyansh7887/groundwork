import os
import json
import logging
from mcp.server.fastmcp import FastMCP
from pipeline import Pipeline

try:
    from qa_agent import QAAgent
except ImportError:
    class QAAgent:
        def index_repository(self, *args, **kwargs): pass
        async def answer_question(self, *args, **kwargs): return {"error": "QA Agent unavailable. Missing dependencies."}

# Configure logging to go to a file to not pollute stdio
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

# Memory cache for graph state
repo_cache = {}

@mcp.tool()
async def analyze_repository(repo_url: str) -> str:
    """
    Runs the full Groundwork pipeline to analyze a GitHub repository.
    Returns the architecture summary and the list of verified claims.
    """
    logger.info(f"Analyzing {repo_url}")
    try:
        final_state = await pipeline.run(repo_url)
        repo_name = final_state["repo_metadata"]["repo"]
        
        # Cache state
        repo_cache[repo_url] = final_state
        
        # Index for Q&A
        qa_agent.index_repository(repo_name, final_state["downloaded_files"], final_state["readme_content"])
        
        result = {
            "architecture_summary": final_state["readme_content"],
            "claims": final_state["claims"]
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.exception("Error during analysis")
        return json.dumps({"error": str(e)})

@mcp.tool()
async def ask_groundwork(repo_url: str, question: str) -> str:
    """
    Asks a grounded question about a previously analyzed repository.
    Returns the answer with verification labels and inline citations.
    """
    if repo_url not in repo_cache:
        return json.dumps({"error": f"Repository '{repo_url}' not analyzed yet. Call analyze_repository first."})
        
    state = repo_cache[repo_url]
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
