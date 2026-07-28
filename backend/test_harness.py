import asyncio
import json
import logging
from ingestor import Ingestor
from cartographer import Cartographer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Small public repos for testing
TEST_REPOS = [
    "https://github.com/encode/starlette",      # Python, FastAPI's foundation
    "https://github.com/pallets/click",         # Python, small CLI library
    "https://github.com/lukeed/kleur"           # JavaScript, small and popular
]

async def run_test(repo_url: str):
    print(f"\n{'='*50}\nTesting Repository: {repo_url}\n{'='*50}")
    
    ingestor = Ingestor()
    cartographer = Cartographer()
    
    try:
        # 1. Ingest repo (gets file tree)
        repo_data = await ingestor.ingest_repository(repo_url)
        files_manifest = repo_data["files"]
        owner = repo_data["owner"]
        repo = repo_data["repo"]
        branch = repo_data["branch"]
        
        # Take a subset of files to avoid long downloads if the repo is large
        # For the test harness, let's limit to 20 files
        test_files = files_manifest[:20]
        print(f"Downloading {len(test_files)} files out of {len(files_manifest)} in-scope files for analysis...")
        
        # 2. Download contents
        downloaded_files = []
        for file_info in test_files:
            path = file_info["path"]
            try:
                content = await ingestor.fetch_file_content(owner, repo, branch, path)
                downloaded_files.append({
                    "path": path,
                    "content": content
                })
            except Exception as e:
                logger.error(f"Failed to fetch {path}: {e}")
                
        # 3. Cartographer analysis
        print("Running Cartographer static analysis...")
        graph = cartographer.analyze_repo(downloaded_files)
        
        # 4. Print Summary
        print(f"\n--- Graph Summary for {repo} ---")
        print(f"Analyzed Files: {len(graph['files'])}")
        print(f"Nodes (Functions/Classes): {len(graph['nodes'])}")
        print(f"Imports: {len(graph['imports'])}")
        print(f"Call Edges: {len(graph['calls'])}")
        print(f"Entry Points: {len(graph['entry_points'])}")
        
        # Print a sample to verify structure
        print("\nSample Nodes:")
        for n in graph["nodes"][:3]:
            print(f"  - {n['id']} (Line {n['line']})")
            
        print("\nSample Calls:")
        for c in graph["calls"][:3]:
            print(f"  - {c['caller_file']} calls {c['callee']} (Line {c['line']})")
            
        print("\nSample Entry Points:")
        for e in graph["entry_points"]:
            print(f"  - {e['id']} (Reason: {e['reason']})")
            
        # Optionally, save to a file for manual inspection
        output_file = f"graph_{repo}.json"
        with open(output_file, "w") as f:
            json.dump(graph, f, indent=2)
        print(f"\nFull graph saved to {output_file}")
            
    except Exception as e:
        print(f"Error testing {repo_url}: {e}")

async def main():
    for repo_url in TEST_REPOS:
        await run_test(repo_url)

if __name__ == "__main__":
    asyncio.run(main())
