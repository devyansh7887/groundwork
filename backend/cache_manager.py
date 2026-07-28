import json
import os
import logging
from typing import Dict, Any, Optional
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cache"

def _cache_path(owner: str, repo: str, sha: str) -> Path:
    return CACHE_DIR / f"{owner}_{repo}_{sha}.json"

def save(owner: str, repo: str, sha: str, state: Dict[str, Any]):
    """Persist pipeline result to disk keyed by repo + SHA."""
    CACHE_DIR.mkdir(exist_ok=True)
    path = _cache_path(owner, repo, sha)
    
    # Only serialize what we need — skip raw file contents (too large)
    payload = {
        "sha": sha,
        "owner": owner,
        "repo": repo,
        "repo_metadata": state.get("repo_metadata", {}),
        "graph": state.get("graph", {}),
        "downloaded_files": state.get("downloaded_files", []),
        "claims": state.get("claims", []),
        "narrative": state.get("narrative", ""),
        "mermaid_diagram": state.get("mermaid_diagram", ""),
        "readme_content": state.get("readme_content", ""),
        "synthesis_retries": state.get("synthesis_retries", 0),
        "pattern_findings": state.get("pattern_findings", []),
        "security_findings": state.get("security_findings", []),
        "actions": state.get("actions", []),
        "cached_at": int(time.time()),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    logger.info(f"💾  Analysis cached — future requests for this SHA will be instant")
    prune()

def prune(max_age_days: int = 3):
    """Delete cache files older than max_age_days to prevent disk bloat."""
    if not CACHE_DIR.exists(): return
    now = time.time()
    cutoff = now - (max_age_days * 86400)
    for p in CACHE_DIR.glob("*.json"):
        if p.stat().st_mtime < cutoff:
            try:
                p.unlink()
                logger.info(f"🧹 Pruned old cache file: {p.name}")
            except Exception as e:
                logger.warning(f"Failed to prune cache {p.name}: {e}")

def load(owner: str, repo: str, sha: str) -> Optional[Dict[str, Any]]:
    """Return cached state if it exists, else None."""
    path = _cache_path(owner, repo, sha)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def find_any_cached(owner: str, repo: str) -> Optional[Dict[str, Any]]:
    """Return the most recent cache entry for a repo (any SHA), used for drift detection."""
    CACHE_DIR.mkdir(exist_ok=True)
    matches = sorted(CACHE_DIR.glob(f"{owner}_{repo}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if matches:
        with open(matches[0], "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def get_cached_sha(owner: str, repo: str) -> Optional[str]:
    """Return the SHA of the most recently cached analysis, if any."""
    cached = find_any_cached(owner, repo)
    return cached.get("sha") if cached else None
