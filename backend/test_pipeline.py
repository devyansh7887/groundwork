import asyncio
import logging
from pipeline import Pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Small public repos for testing
TEST_REPOS = [
    "https://github.com/expressjs/express",      # Python, FastAPI's foundation
    "https://github.com/pallets/click",         # Python, small CLI library
    "https://github.com/lukeed/kleur"           # JavaScript, small and popular
]

async def run_test(repo_url: str):
    print(f"\n{'='*50}\nTesting Pipeline: {repo_url}\n{'='*50}")
    pipeline = Pipeline()
    
    try:
        final_state = await pipeline.run(repo_url)
        
        repo_name = final_state["repo_metadata"]["repo"]
        readme_file = f"README_{repo_name}.md"
        
        with open(readme_file, "w", encoding="utf-8") as f:
            f.write(final_state["readme_content"])
            
        print(f"\nSuccessfully generated {readme_file}")
    except Exception as e:
        logger.error(f"Error testing {repo_url}: {e}", exc_info=True)

async def main():
    for repo_url in TEST_REPOS:
        await run_test(repo_url)

if __name__ == "__main__":
    asyncio.run(main())
