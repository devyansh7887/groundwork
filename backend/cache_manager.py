"""
cache_manager.py — Dual-layer persistence for Groundwork pipeline results.

PRIMARY:   SQLite database (groundwork_cache.db) — survives server restarts,
           Render deploys, and free-tier sleep cycles.
FALLBACK:  JSON files in backend/cache/ — used if SQLite is unavailable.

The in-memory dict in main.py is still the fastest path (microseconds).
SQLite is the persistent source of truth that re-hydrates it on every startup.
"""
import json
import os
import sqlite3
import logging
import time
from typing import Dict, Any, Optional
from pathlib import Path
import threading

logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────
CACHE_DIR = Path(__file__).parent / "cache"
DB_PATH   = Path(__file__).parent / "groundwork_cache.db"

# ── Thread-local SQLite connections (SQLite connections are not thread-safe) ──
_local = threading.local()

def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.execute("PRAGMA journal_mode=WAL")   # safe concurrent writes
        _local.conn.execute("PRAGMA synchronous=NORMAL") # faster than FULL, still durable
        _local.conn.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                owner       TEXT NOT NULL,
                repo        TEXT NOT NULL,
                sha         TEXT NOT NULL,
                cached_at   INTEGER NOT NULL,
                payload     TEXT NOT NULL,
                PRIMARY KEY (owner, repo, sha)
            )
        """)
        _local.conn.commit()
    return _local.conn


# ── Public API ───────────────────────────────────────────────────────────────

def save(owner: str, repo: str, sha: str, state: Dict[str, Any]):
    """Persist pipeline result — writes to both SQLite and JSON fallback."""
    payload = _build_payload(owner, repo, sha, state)
    payload_json = json.dumps(payload, default=str)

    # ── SQLite ────────────────────────────────────────────────────────────────
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO analyses (owner, repo, sha, cached_at, payload) VALUES (?, ?, ?, ?, ?)",
            (owner, repo, sha, payload["cached_at"], payload_json),
        )
        conn.commit()
        logger.info("💾  Analysis persisted to SQLite — survives restarts")
    except Exception as e:
        logger.warning(f"SQLite write failed ({e}), falling back to JSON only")

    # ── JSON fallback ─────────────────────────────────────────────────────────
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        path = CACHE_DIR / f"{owner}_{repo}_{sha}.json"
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload_json)
    except Exception as e:
        logger.warning(f"JSON cache write failed: {e}")

    prune()


def load(owner: str, repo: str, sha: str) -> Optional[Dict[str, Any]]:
    """Return cached state for exact SHA, or None."""
    # Try SQLite first
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT payload FROM analyses WHERE owner=? AND repo=? AND sha=?",
            (owner, repo, sha),
        ).fetchone()
        if row:
            return json.loads(row[0])
    except Exception as e:
        logger.warning(f"SQLite read failed ({e}), falling back to JSON")

    # JSON fallback
    path = CACHE_DIR / f"{owner}_{repo}_{sha}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    return None


def find_any_cached(owner: str, repo: str) -> Optional[Dict[str, Any]]:
    """Return the most recent cached analysis for a repo (any SHA)."""
    # Try SQLite first
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT payload FROM analyses WHERE owner=? AND repo=? ORDER BY cached_at DESC LIMIT 1",
            (owner, repo),
        ).fetchone()
        if row:
            return json.loads(row[0])
    except Exception as e:
        logger.warning(f"SQLite find_any failed ({e}), falling back to JSON")

    # JSON fallback
    CACHE_DIR.mkdir(exist_ok=True)
    matches = sorted(
        CACHE_DIR.glob(f"{owner}_{repo}_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if matches:
        with open(matches[0], "r", encoding="utf-8") as f:
            return json.load(f)

    return None


def get_cached_sha(owner: str, repo: str) -> Optional[str]:
    """Return the SHA of the most recently cached analysis, if any."""
    cached = find_any_cached(owner, repo)
    return cached.get("sha") if cached else None


def prune(max_age_days: int = 7):
    """Delete old entries from SQLite and JSON files to prevent storage bloat."""
    cutoff = int(time.time()) - (max_age_days * 86400)

    # SQLite prune
    try:
        conn = _get_conn()
        deleted = conn.execute(
            "DELETE FROM analyses WHERE cached_at < ?", (cutoff,)
        ).rowcount
        conn.commit()
        if deleted:
            logger.info(f"🧹  Pruned {deleted} old SQLite cache entries (>{max_age_days}d old)")
    except Exception as e:
        logger.warning(f"SQLite prune failed: {e}")

    # JSON prune
    if not CACHE_DIR.exists():
        return
    now = time.time()
    file_cutoff = now - (max_age_days * 86400)
    for p in CACHE_DIR.glob("*.json"):
        if p.stat().st_mtime < file_cutoff:
            try:
                p.unlink()
                logger.info(f"🧹  Pruned old JSON cache: {p.name}")
            except Exception as e:
                logger.warning(f"Failed to prune {p.name}: {e}")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_payload(owner: str, repo: str, sha: str, state: Dict[str, Any]) -> Dict[str, Any]:
    return {
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
