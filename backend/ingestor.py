import httpx
import logging
from typing import List, Dict, Any, Optional
from config import GITHUB_TOKEN, MAX_FILES, MAX_LOC, SUPPORTED_LANGUAGES, LANGUAGE_EXTENSIONS, DEFAULT_BRANCH_ONLY, PUBLIC_REPOS_ONLY, SMART_SAMPLE_TARGET

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RepoScopeError(Exception):
    pass

class Ingestor:
    def __init__(self, session_token: Optional[str] = None):
        self.session_token = session_token
        self.client = httpx.AsyncClient(follow_redirects=True, timeout=30.0)
        
    async def _fetch(self, url: str) -> httpx.Response:
        from key_pool import key_pool
        import time
        max_retries = 6
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
                if self.session_token:
                    raise RepoScopeError("Your provided GitHub token has exceeded its rate limit.")
                logger.warning(f"Rate limit hit. Rotating key...")
                continue
                
            return response
            
        raise RepoScopeError("All GitHub tokens have exhausted their rate limits.")
        
    async def close(self):
        await self.client.aclose()

    def parse_github_url(self, url: str) -> tuple[str, str]:
        """Extracts owner and repo from a GitHub URL."""
        url = url.rstrip('/')
        parts = url.split('/')
        if "github.com" not in parts or len(parts) < 2:
            raise ValueError("Invalid GitHub URL")
        
        # e.g. https://github.com/owner/repo
        repo = parts[-1]
        owner = parts[-2]
        if repo.endswith(".git"):
            repo = repo[:-4]
        return owner, repo

    async def get_repo_metadata(self, owner: str, repo: str) -> Dict[str, Any]:
        """Fetches repo metadata to check visibility and default branch."""
        url = f"https://api.github.com/repos/{owner}/{repo}"
        response = await self._fetch(url)
        if response.status_code == 404:
            raise RepoScopeError(f"Repository {owner}/{repo} not found or is private.")
        response.raise_for_status()
        data = response.json()
        
        if PUBLIC_REPOS_ONLY and data.get("private", True):
            raise RepoScopeError("Only public repositories are supported.")
        
        return {
            "default_branch": data.get("default_branch", "main"),
            "visibility": data.get("visibility"),
            "stargazers_count": data.get("stargazers_count", 0),
            "description": data.get("description", ""),
            "language": data.get("language", ""),
            "forks_count": data.get("forks_count", 0),
            "open_issues_count": data.get("open_issues_count", 0),
        }

    async def get_file_tree(self, owner: str, repo: str, branch: str) -> List[Dict[str, Any]]:
        """Fetches the recursive file tree from GitHub."""
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        response = await self._fetch(url)
        response.raise_for_status()
        data = response.json()
        
        if data.get("truncated"):
            logger.warning("GitHub API returned a truncated tree.")
            
        return data.get("tree", [])

    def filter_tree(self, tree: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Filters the tree to only include supported languages and files.
        Returns both the filtered list AND total counts for accurate stats reporting.
        """
        supported_exts = []
        for exts in LANGUAGE_EXTENSIONS.values():
            supported_exts.extend(exts)
            
        filtered_files = []
        ignore_dirs = ["node_modules", "build", "dist", ".gradle", ".idea", "venv", "out", "target", "__pycache__", ".next"]
        total_blobs = 0
        excluded_by_dir = 0
        excluded_by_size = 0
        excluded_by_ext = 0
        
        for item in tree:
            if item["type"] == "blob":
                total_blobs += 1
                path = item["path"]
                size = item.get("size", 0)
                
                # Exclude common build and dependency directories
                if any(f"/{d}/" in f"/{path}" or path.startswith(f"{d}/") for d in ignore_dirs):
                    excluded_by_dir += 1
                    continue
                    
                # Exclude massive files (> 200 KB) to prevent Render memory OOM
                if size > 200 * 1024:
                    excluded_by_size += 1
                    continue
                
                if any(path.endswith(ext) for ext in supported_exts):
                    filtered_files.append(item)
                else:
                    excluded_by_ext += 1
                    
        logger.info(
            f"📁  Tree filter: {total_blobs} total blobs → "
            f"{len(filtered_files)} code files in scope "
            f"({excluded_by_dir} in build dirs, {excluded_by_size} oversized, {excluded_by_ext} unsupported ext)"
        )
        return {
            "files": filtered_files,
            "total_blobs": total_blobs,
            "in_scope": len(filtered_files),
            "excluded_by_dir": excluded_by_dir,
            "excluded_by_size": excluded_by_size,
            "excluded_by_ext": excluded_by_ext,
        }

    async def fetch_file_content(self, owner: str, repo: str, branch: str, file_path: str) -> str:
        """Fetches raw file content."""
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"
        response = await self._fetch(url)
        response.raise_for_status()
        return response.text

    def _smart_sample(self, files: List[Dict[str, Any]], target: int) -> List[Dict[str, Any]]:
        """
        Picks the most architecturally important files up to `target` count.

        Priority tiers (highest to lowest):
          Tier 1 — Named entry points: main.*, index.*, app.*, server.*, __init__.py
                   at the repo root or package root. These define the public surface.
          Tier 2 — Root-level files: anything at depth 0 or 1. Config, setup, core modules.
          Tier 3 — Core non-test files, sorted by size descending.
                   Larger files = more code = more architecturally significant.
          Tier 4 — Test/fixture files, sorted by size descending.
                   Included last to fill any remaining budget.

        This gives a principled, repeatable sample — not random. The same repo
        always produces the same sample, so cached results remain valid.
        """
        ENTRY_POINT_STEMS = {
            'main', 'index', 'app', 'server', 'application', '__init__',
            'manage', 'cli', 'run', 'wsgi', 'asgi', 'setup', 'configure',
            'start', 'launch', 'entrypoint', 'entry', 'init', 'bootstrap',
        }
        TEST_INDICATORS = [
            '/test/', '/tests/', '/spec/', '/specs/', '/__tests__/',
            '_test.', '.test.', '_spec.', '.spec.', '/fixtures/', '/mocks/',
        ]

        tier1, tier2, tier3, tier4 = [], [], [], []

        for f in files:
            path = f['path']
            path_lower = path.lower()
            depth = path.count('/')
            stem = path_lower.split('/')[-1].rsplit('.', 1)[0]  # filename without extension
            size = f.get('size', 0)

            is_test = any(ind in f'/{path_lower}' for ind in TEST_INDICATORS)
            is_entry = stem in ENTRY_POINT_STEMS
            is_shallow = depth <= 1  # root or one directory deep

            if is_entry:
                tier1.append((size, path, f))
            elif is_shallow and not is_test:
                tier2.append((size, path, f))
            elif not is_test:
                tier3.append((size, path, f))
            else:
                tier4.append((size, path, f))

        # Sort each tier by size descending (larger = more important)
        for tier in (tier1, tier2, tier3, tier4):
            tier.sort(key=lambda x: x[0], reverse=True)

        selected = []
        seen = set()
        for tier in (tier1, tier2, tier3, tier4):
            for size, path, f in tier:
                if len(selected) >= target:
                    break
                if path not in seen:
                    selected.append(f)
                    seen.add(path)
            if len(selected) >= target:
                break

        logger.info(
            f"🎯  Smart sampled {len(selected)}/{len(files)} files "
            f"({len(tier1)} entry points, {len(tier2)} shallow core, "
            f"{len(tier3)} deep core, {len(tier4)} test files in full set)"
        )
        return selected

    async def ingest_repository(self, url: str) -> Dict[str, Any]:
        """Main entry point to ingest and validate a repository."""
        owner, repo = self.parse_github_url(url)
        logger.info(f"📡  Reaching out to GitHub for {owner}/{repo}...")
        
        # 1. Get metadata
        metadata = await self.get_repo_metadata(owner, repo)
        branch = metadata["default_branch"]
        logger.info(f"🌿  Found branch '{branch}' — scanning file tree...")
        
        # 2. Get tree
        tree = await self.get_file_tree(owner, repo, branch)
        
        # 3. Filter tree — returns dict with counts for accurate stats
        filter_result = self.filter_tree(tree)
        in_scope_files = filter_result["files"]
        original_file_count = len(in_scope_files)
        
        logger.info(f"📁  {original_file_count} source files in scope (out of {filter_result['total_blobs']} total blobs)")
        
        # 4. Absolute hard cap — repos with >1000 source files are data/asset repos,
        #    not codebases. Smart sampling cannot meaningfully represent them.
        if original_file_count > MAX_FILES:
            raise RepoScopeError(
                f"Repository has {original_file_count} source files — this looks like a data or "
                f"monorepo rather than a single codebase (limit: {MAX_FILES}). "
                f"Try analyzing a specific sub-package instead."
            )
        
        # 5. Smart sampling — triggered when file count exceeds SMART_SAMPLE_TARGET.
        #    We never silently drop files. Instead we rank by architectural importance
        #    and surface this to the user via the 'sampled' flag in the response.
        sampled = False
        if original_file_count > SMART_SAMPLE_TARGET:
            logger.info(
                f"📊  {original_file_count} files exceeds target ({SMART_SAMPLE_TARGET}). "
                f"Running smart sampler — prioritising entry points and core modules..."
            )
            in_scope_files = self._smart_sample(in_scope_files, SMART_SAMPLE_TARGET)
            sampled = True
            logger.info(f"✅  Smart sample complete — analysing {len(in_scope_files)} of {original_file_count} files")
        else:
            logger.info(f"📦  {original_file_count} files — fetching all contents...")
        
        return {
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "files": in_scope_files,
            "file_count": len(in_scope_files),
            # Accurate stats — never lie about what we read
            "total_blobs": filter_result["total_blobs"],
            "in_scope_files": original_file_count,     # total BEFORE sampling
            "analysed_files": len(in_scope_files),      # total AFTER sampling
            "sampled": sampled,
            "original_file_count": original_file_count,
            "excluded_build_dirs": filter_result["excluded_by_dir"],
            "excluded_oversized": filter_result["excluded_by_size"],
            "repo_meta": metadata,
        }

    async def get_current_sha(self, owner: str, repo: str, branch: str) -> str:
        """Fetches the current HEAD commit SHA for cache invalidation."""
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
        response = await self._fetch(url)
        response.raise_for_status()
        return response.json().get("sha", "")[:12]  # short SHA is enough for cache key

# For testing
if __name__ == "__main__":
    import asyncio
    async def test():
        ingestor = Ingestor()
        try:
            # Let's test with a small public repo
            res = await ingestor.ingest_repository("https://github.com/encode/starlette")
            print(f"Ingested {res['file_count']} files from {res['repo']}")
        except Exception as e:
            print(f"Error: {e}")
            
    asyncio.run(test())
