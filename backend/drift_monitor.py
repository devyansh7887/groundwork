import os
import sys
import json
import asyncio
import logging
from config import GITHUB_TOKEN
from ingestor import Ingestor
from cartographer import Cartographer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_drift_monitor(repo_url: str):
    logger.info(f"Running Drift Monitor on {repo_url}")
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN is missing. Cannot monitor drift.")
        sys.exit(1)

    ingestor = Ingestor()
    cartographer = Cartographer()

    logger.info("Fetching latest files...")
    files = await ingestor.ingest_repository(repo_url)
    
    logger.info("Running Cartographer...")
    graph = cartographer.build_graph(files)
    
    # In a real deployed version, we would load the previous graph from a database or artifact
    # and compare the entry_points and calls to see if anything changed.
    # For this implementation, we will save the graph to a local file and simulate a check.
    
    cache_file = f"{repo_url.split('/')[-1]}_latest_graph.json"
    
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            old_graph = json.load(f)
            
        old_nodes = len(old_graph.get("nodes", []))
        new_nodes = len(graph.get("nodes", []))
        
        if old_nodes != new_nodes:
            logger.warning(f"DRIFT DETECTED: Node count changed from {old_nodes} to {new_nodes}")
            # This is where we would trigger the Doc Writer to update stale sections
        else:
            logger.info("No structural drift detected since last run.")
            
    with open(cache_file, "w") as f:
        json.dump(graph, f)
        
    print(f"Drift monitor check complete for {repo_url}.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        repo = sys.argv[1]
    else:
        repo = "https://github.com/encode/starlette"
    asyncio.run(run_drift_monitor(repo))
