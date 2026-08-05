import asyncio
import httpx
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class GitBlameAnalyzer:
    def __init__(self, session_token: str | None = None):
        self.session_token = session_token
        self.client = httpx.AsyncClient(follow_redirects=True, timeout=10.0)
        
    async def fetch_file_commits(self, owner: str, repo: str, path: str) -> List[Dict[str, Any]]:
        """Fetch the commit history for a single file."""
        from key_pool import key_pool
        url = f"https://api.github.com/repos/{owner}/{repo}/commits?path={path}&per_page=10"
        
        max_retries = 3
        for attempt in range(max_retries):
            token = self.session_token or key_pool.get_best_key()
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Groundwork-Agent"
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"
                
            response = await self.client.get(url, headers=headers)
            remaining = int(response.headers.get("x-ratelimit-remaining", -1))
            reset_time = int(response.headers.get("x-ratelimit-reset", 0))
            
            if token and not self.session_token and remaining != -1:
                key_pool.update_key_status(token, remaining, reset_time)
            
            if response.status_code in [403, 429] and remaining == 0:
                logger.warning(f"Rate limit hit during blame. Rotating key...")
                continue
                
            if response.status_code == 200:
                return response.json()
            return []
                
        return []

    async def close(self):
        await self.client.aclose()

    async def analyze_authors(self, owner: str, repo: str, files: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Returns a map of file_path -> { primary_author: str, authors: {name: count} }
        """
        logger.info(f"🕵️  Fetching author history for {len(files)} files...")
        
        sem = asyncio.Semaphore(10) # 10 concurrent requests
        results = {}
        
        async def process_file(path: str):
            async with sem:
                commits = await self.fetch_file_commits(owner, repo, path)
                author_counts = {}
                for c in commits:
                    author_name = "Unknown"
                    if c.get("author") and c["author"].get("login"):
                        author_name = c["author"]["login"]
                    elif c.get("commit") and c["commit"].get("author"):
                        author_name = c["commit"]["author"].get("name", "Unknown")
                        
                    author_counts[author_name] = author_counts.get(author_name, 0) + 1
                
                if author_counts:
                    primary = max(author_counts.items(), key=lambda x: x[1])[0]
                    results[path] = {
                        "primary_author": primary,
                        "authors": author_counts
                    }
                else:
                    results[path] = {
                        "primary_author": "Unknown",
                        "authors": {"Unknown": 1}
                    }

        tasks = [process_file(f) for f in files]
        await asyncio.gather(*tasks)
        
        logger.info(f"✅  Author history mapped for {len(results)} files")
        return results
