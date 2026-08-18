import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pipeline import Pipeline
import contextvars
import asyncio
import json
import os
import re

try:
    from qa_agent import QAAgent
except ImportError:
    class QAAgent:
        def index_repository(self, *args, **kwargs): pass
        async def answer_question(self, *args, **kwargs): return {"error": "QA Agent unavailable. Missing dependencies."}

from onboarding_agent import OnboardingAgent
from contribution_drafter import ContributionDrafter, ContributionGuide, find_relevant_files
from contribution_qa import contribution_qa
import cache_manager
from ingestor import Ingestor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory cache (mirrors disk cache for fast access)
repo_cache: dict = {}

def _hydrate_cache_from_disk():
    """On startup: scan all disk cache files and populate repo_cache so /api/qa
    and /api/draft work immediately without re-analyzing after a restart."""
    from pathlib import Path
    cache_dir = Path(__file__).parent / "cache"
    if not cache_dir.exists():
        return
    loaded = 0
    for cache_file in sorted(cache_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            owner = state.get("owner", "")
            repo  = state.get("repo", "")
            if owner and repo:
                canonical_url = f"https://github.com/{owner}/{repo}"
                if canonical_url not in repo_cache:
                    repo_cache[canonical_url] = state
                    loaded += 1
        except Exception as e:
            logger.warning(f"Failed to load cache file {cache_file.name}: {e}")
    if loaded:
        logger.info(f"♻️  Hydrated {loaded} repo(s) from disk cache — /api/qa and /api/draft are ready immediately.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    _hydrate_cache_from_disk()
    yield

app = FastAPI(title="Groundwork API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = Pipeline()
qa_agent = QAAgent()
onboarding_agent = OnboardingAgent()
drafter = ContributionDrafter()



# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Simple health check used by the frontend to detect backend readiness."""
    return {"status": "ok", "version": "1.0.0"}

# ─── Models ───────────────────────────────────────────────────────────────────

# ─── Helpers ──────────────────────────────────────────────────────────────────

def extract_token(req: Request) -> str | None:
    auth = req.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:]
    return None

from pydantic import BaseModel, field_validator

class AnalyzeRequest(BaseModel):
    repo_url: str
    mode: str = "technical"
    force_refresh: bool = False

    @field_validator("repo_url")
    def validate_url(cls, v):
        if not re.match(r"^https://github\.com/[\w.-]+/[\w.-]+/?$", v):
            raise ValueError("Invalid GitHub repository URL")
        return v

class ResynthesizeRequest(BaseModel):
    repo_url: str
    mode: str = "technical"
    
    @field_validator("repo_url")
    def validate_url(cls, v):
        if not re.match(r"^https://github\.com/[\w.-]+/[\w.-]+/?$", v):
            raise ValueError("Invalid GitHub repository URL")
        return v

class QARequest(BaseModel):
    repo_url: str
    question: str
    
    @field_validator("repo_url")
    def validate_url(cls, v):
        if not re.match(r"^https://github\.com/[\w.-]+/[\w.-]+/?$", v):
            raise ValueError("Invalid GitHub repository URL")
        return v

class OnboardRequest(BaseModel):
    repo_url: str
    role: str
    level: str
    
    @field_validator("repo_url")
    def validate_url(cls, v):
        if not re.match(r"^https://github\.com/[\w.-]+/[\w.-]+/?$", v):
            raise ValueError("Invalid GitHub repository URL")
        return v

class DraftRequest(BaseModel):
    repo_url: str
    action: dict | None = None
    issue: dict | None = None
    issue_number: int | None = None  # New: reference to a GitHub issue by number
    
    @field_validator("repo_url")
    def validate_url(cls, v):
        if not re.match(r"^https://github\.com/[\w.-]+/[\w.-]+/?$", v):
            raise ValueError("Invalid GitHub repository URL")
        return v

class ContributionQARequest(BaseModel):
    repo_url: str
    question: str
    issue_title: str = ""
    understanding: str = ""
    what_needs_to_change: str = ""
    target_files: list[str] = []

    @field_validator("repo_url")
    def validate_url(cls, v):
        if not re.match(r"^https://github\.com/[\w.-]+/[\w.-]+/?$", v):
            raise ValueError("Invalid GitHub repository URL")
        return v

class IssuesRequest(BaseModel):
    repo_url: str
    
    @field_validator("repo_url")
    def validate_url(cls, v):
        if not re.match(r"^https://github\.com/[\w.-]+/[\w.-]+/?$", v):
            raise ValueError("Invalid GitHub repository URL")
        return v

# ─── SSE Logging ──────────────────────────────────────────────────────────────

log_queue_var = contextvars.ContextVar('log_queue', default=None)

ALLOWED_LOG_MODULES = {"ingestor", "pipeline", "cartographer", "synthesizer", "verifier", "diagram_agent", "git_blame", "__main__"}

class QueueHandler(logging.Handler):
    def emit(self, record):
        if record.name not in ALLOWED_LOG_MODULES:
            return
        q_data = log_queue_var.get()
        if q_data is not None:
            # We unpack (loop, queue) stored by the request thread
            try:
                loop, q = q_data
                msg = self.format(record)
                
                # Clean up ugly LLM validation traces for the user UI
                if "LLM attempt" in msg and "failed:" in msg:
                    msg = "⚠️ AI response validation failed. Retrying..."
                elif "Synthesizer attempt" in msg and "failed:" in msg:
                    msg = "⚠️ AI response validation failed. Retrying..."
                elif "Verifier LLM fallback failed:" in msg:
                    msg = "⚠️ AI verifier fallback failed. Proceeding with defaults."
                    
                loop.call_soon_threadsafe(q.put_nowait, msg)
            except Exception:
                pass

queue_handler = QueueHandler()
queue_handler.setFormatter(logging.Formatter('%(message)s'))
logging.getLogger().addHandler(queue_handler)

# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _run_and_cache(repo_url: str, session_token: str | None, mode: str, force_refresh: bool = False) -> dict:
    """Full pipeline run with SHA-based cache check."""
    ingestor = Ingestor(session_token)
    owner, repo_name = ingestor.parse_github_url(repo_url)

    try:
        # Get metadata to find branch + current SHA
        metadata = await ingestor.get_repo_metadata(owner, repo_name)
        branch = metadata["default_branch"]

        logger.info(f"🔎  Checking for cached analysis...")
        sha = await ingestor.get_current_sha(owner, repo_name, branch)
    except Exception as e:
        logger.warning(f"GitHub API failed: {e}. Attempting to load from cache offline.")
        cached = cache_manager.find_any_cached(owner, repo_name)
        if cached:
            logger.info(f"⚡  Cache hit (offline fallback)! Loading previous analysis...")
            repo_cache[repo_url] = cached
            return cached
        raise e

    cached = None
    if not force_refresh:
        cached = cache_manager.load(owner, repo_name, sha)
        if not cached:
            # Fallback to any cached version for this repo (e.g. for the demo repo if it drifted)
            cached = cache_manager.find_any_cached(owner, repo_name)

    if cached:
        logger.info(f"⚡  Cache hit! Loading previous analysis in milliseconds...")
        repo_cache[repo_url] = cached
        return cached

    logger.info(f"🆕  No cache found — running full analysis (this takes ~60s the first time)...")
    final_state = await pipeline.run(repo_url, session_token, mode)

    # Persist to disk
    cache_manager.save(owner, repo_name, sha, final_state)
    final_state["sha"] = sha
    repo_cache[repo_url] = final_state
    return final_state

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Groundwork agents are awake."}

@app.get("/api/key-status")
def key_status():
    """Returns current rate limit status for all pool keys."""
    from key_pool import key_pool
    from llm_key_pool import llm_key_pool
    keys = key_pool.get_status()
    keys.extend(llm_key_pool.get_status())
    return {"keys": keys}

@app.post("/api/analyze")
async def analyze_repo(req: AnalyzeRequest, request: Request):
    session_token = extract_token(request)
    async def event_generator():
        q = asyncio.Queue()
        log_queue_var.set((asyncio.get_running_loop(), q))
        q.put_nowait(f"🚀  Starting analysis of {req.repo_url}...")

        # Hard 9-minute timeout so a silent hang gives a real error instead of a dropped connection
        task = asyncio.create_task(
            asyncio.wait_for(
                _run_and_cache(req.repo_url, session_token, req.mode, req.force_refresh),
                timeout=540.0
            )
        )

        while not task.done():
            try:
                msg = await asyncio.wait_for(q.get(), timeout=4.0)
                try:
                    yield f"data: {json.dumps({'log': msg})}\n\n"
                except (TypeError, ValueError):
                    yield f"data: {json.dumps({'log': str(msg)})}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'log': '⏳  AI agents are working... hang tight'})}\n\n"

        while not q.empty():
            try:
                msg = q.get_nowait()
                yield f"data: {json.dumps({'log': str(msg)})}\n\n"
            except Exception:
                pass

        try:
            final_state = task.result()
            qa_agent.index_repository(
                final_state["repo_metadata"].get("repo", ""),
                final_state.get("downloaded_files", []),
                final_state.get("readme_content", ""),
                session_token
            )
            graph = final_state.get("graph", {})
            downloaded = final_state.get("downloaded_files", [])
            repo_meta = final_state.get("repo_metadata", {})

            total_sloc = graph.get("total_sloc", 0)
            public_functions = graph.get("total_public_functions", len(graph.get("nodes", [])))
            in_scope_files = repo_meta.get("in_scope_files", len(graph.get("files", [])))
            total_blobs = repo_meta.get("total_blobs", in_scope_files)

            file_locs_sloc = {}
            for f in downloaded:
                path = f.get("path", "")
                content = f.get("content") or ""
                sloc = sum(
                    1 for line in content.splitlines()
                    if line.strip() and not line.strip().startswith(('#', '//', '*', '/*'))
                )
                file_locs_sloc[path] = sloc

            result = {
                "readme": final_state.get("readme_content", ""),
                "diagram": final_state.get("mermaid_diagram", ""),
                "claims": final_state.get("claims", []),
                "from_cache": "sha" in final_state,
                "graph": graph,
                "security": final_state.get("security_findings", []),
                "patterns": final_state.get("pattern_findings", []),
                "actions": final_state.get("actions", []),
                "file_sizes": {
                    f.get("path", ""): len(f.get("content", ""))
                    for f in final_state.get("downloaded_files", [])
                },
                "file_locs": {
                    f.get("path", ""): (f.get("content") or "").count("\n") + 1
                    for f in final_state.get("downloaded_files", [])
                },
            }
            yield f"data: {json.dumps({'result': result})}\n\n"
        except BaseException as e:
            # Catch BaseException (not just Exception) to also handle
            # asyncio.CancelledError, asyncio.TimeoutError, MemoryError, etc.
            error_msg = str(e) or type(e).__name__
            logger.exception("Error during analysis:")
            is_rate_limit = "rate limit" in error_msg.lower() or "429" in error_msg
            is_timeout = "timed out" in error_msg.lower() or isinstance(e, asyncio.TimeoutError)
            if is_timeout:
                error_msg = "Analysis timed out — repository may be too large or AI services are under heavy load. Please try again or try a smaller repository."
            yield f"data: {json.dumps({'error': error_msg, 'rate_limit': is_rate_limit})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

@app.post("/api/resynthesize")
async def resynthesize(req: ResynthesizeRequest, request: Request):
    session_token = extract_token(request)
    """Re-run only the synthesis step on a cached graph. Fast — no GitHub calls."""
    if req.repo_url not in repo_cache:
        raise HTTPException(status_code=404, detail="Repository not in cache. Run a full analysis first.")

    state = repo_cache[req.repo_url]
    from synthesizer import Synthesizer
    synth = Synthesizer()

    result = synth.synthesize(
        state["graph"],
        state.get("downloaded_files", []),
        mode=req.mode,
        session_token=session_token
    )

    # Update cached narrative
    repo_cache[req.repo_url]["narrative"] = result["narrative"]
    repo_cache[req.repo_url]["claims"] = result["claims"]

    readme = f"# Groundwork Architecture Analysis\n\n## Architecture Overview\n\n{result['narrative']}\n\n"
    readme += f"## Component Diagram\n\n```mermaid\n{state.get('mermaid_diagram', '')}\n```\n\n"

    return {
        "readme": readme,
        "diagram": state.get("mermaid_diagram", ""),
        "claims": result["claims"],
    }

@app.get("/api/drift")
async def check_drift(repo_url: str):
    """Check if the cached analysis is stale vs current HEAD SHA."""
    if repo_url not in repo_cache:
        raise HTTPException(status_code=404, detail="Repository not in cache.")

    state = repo_cache[repo_url]
    owner = state["repo_metadata"].get("owner", "")
    repo_name = state["repo_metadata"].get("repo", "")
    branch = state["repo_metadata"].get("default_branch", "main")

    try:
        ingestor = Ingestor()
        current_sha = await ingestor.get_current_sha(owner, repo_name, branch)
        cached_sha = state.get("sha", "")
        is_stale = current_sha != cached_sha
        return {"stale": is_stale, "cached_sha": cached_sha, "current_sha": current_sha}
    except Exception as e:
        return {"stale": False, "error": str(e)}

@app.post("/api/qa")
async def ask_question(req: QARequest, request: Request):
    session_token = extract_token(request)
    if req.repo_url not in repo_cache:
        raise HTTPException(status_code=400, detail="Repository not analyzed yet.")
    state = repo_cache[req.repo_url]
    repo_name = state["repo_metadata"].get("repo", "")
    res = await qa_agent.answer_question(repo_name, req.question, state["graph"], state.get("downloaded_files", []), session_token)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@app.post("/api/onboard")
async def generate_path(req: OnboardRequest, request: Request):
    session_token = extract_token(request)
    if req.repo_url not in repo_cache:
        raise HTTPException(status_code=400, detail="Repository not analyzed yet.")
    state = repo_cache[req.repo_url]
    path = onboarding_agent.generate_path(req.role, req.level, state["graph"], state.get("narrative", ""), session_token)
    return path.model_dump()

@app.post("/api/draft")
async def draft_contribution(req: DraftRequest, request: Request):
    session_token = extract_token(request)
    if req.repo_url not in repo_cache:
        raise HTTPException(status_code=400, detail="Repository not analyzed yet.")
    
    state = repo_cache[req.repo_url]
    
    if req.action:
        # Action-specific draft: use the LLM to generate a real diff patch
        target = req.action.get("target_file", "")
        title = req.action.get("title", "Fix codebase issue")
        description = req.action.get("description", "")
        action_text = req.action.get("action", "")
        
        # Find the actual file contents for context
        downloaded_files = state.get("downloaded_files", [])
        relevant_files = [f for f in downloaded_files if f.get("path", "") == target]
        if not relevant_files:
            # Fallback: pick the first few files
            relevant_files = downloaded_files[:3]
        
        # Build a synthetic issue dict so we can reuse draft_patch
        synthetic_issue = {
            "title": title,
            "body": f"""## Issue: {title}

**Description:** {description}

**Required Action:** {action_text}

**Target File:** {target}

**Impact:** {req.action.get('impact', '')}

Please provide a concrete code patch (unified diff format with +/- lines and line numbers) that fixes this issue in {target}.
Include:
1. The exact lines to change (use --- a/file and +++ b/file format)
2. Context lines for clarity
3. A test to verify the fix works
"""
        }
        
        try:
            patch = drafter.draft_patch(synthetic_issue, state["graph"], relevant_files + downloaded_files[:5], session_token)
            return patch.model_dump()
        except Exception as e:
            logger.error(f"LLM draft failed: {e}")
            return {
                "issue_title": title,
                "target_file": target,
                "diff": f"--- a/{target}\n+++ b/{target}\n@@ -1,1 +1,1 @@\n# [AI Draft Unavailable]\n# The drafting service is currently rate-limited or unavailable.\n# Please write the code to address: {action_text}",
                "test_code": f"// The AI drafting service is currently rate-limited.\n// Please write tests for {target} to verify the fix.",
                "pr_description": f"## {title}\n\n{description}\n\n**Action:** {action_text}\n\n**Impact:** {req.action.get('impact', '')}"
            }
    elif req.issue:
        # Real GitHub issue → generate full ContributionGuide
        owner = state["repo_metadata"].get("owner", "")
        repo = state["repo_metadata"].get("repo", "")
        try:
            guide = drafter.draft_contribution_guide(
                issue=req.issue,
                graph=state["graph"],
                downloaded_files=state.get("downloaded_files", []),
                owner=owner,
                repo=repo,
                session_token=session_token
            )
            return guide.model_dump()
        except Exception as e:
            logger.error(f"ContributionGuide generation failed: {e}")
            return {
                "issue_title": req.issue.get("title", "Issue"),
                "issue_url": f"https://github.com/{owner}/{repo}/issues/{req.issue.get('number', '')}",
                "difficulty": "medium",
                "difficulty_reason": "Could not estimate difficulty.",
                "target_files": [],
                "understanding": "AI service unavailable. Please retry.",
                "what_needs_to_change": "Please retry.",
                "diff": f"# Draft failed: {str(e)}",
                "test_code": "",
                "pr_title": f"Fix: {req.issue.get('title', '')}",
                "pr_description": f"Fixes #{req.issue.get('number', '')}",
                "confidence": "low",
                "confidence_reason": f"AI service failed: {str(e)}"
            }
    else:
        # Generic fallback: find a good first issue on GitHub
        owner = state["repo_metadata"].get("owner", "")
        repo = state["repo_metadata"].get("repo", "")
        issues = await drafter.fetch_issues(owner, repo, session_token)
        ranked = drafter.rank_issues(issues, state["graph"])
        if not ranked:
            return {"message": "No open issues found in this repository."}
        # Return the top-ranked (easiest) issue as a suggestion
        return {"suggested_issue": ranked[0], "message": "Select an issue from the Issues tab to start your contribution."}

@app.post("/api/issues")
async def get_issues(req: IssuesRequest, request: Request):
    session_token = extract_token(request)
    if req.repo_url not in repo_cache:
        raise HTTPException(status_code=400, detail="Repository not analyzed yet.")
    state = repo_cache[req.repo_url]
    owner = state["repo_metadata"].get("owner", "")
    repo = state["repo_metadata"].get("repo", "")
    if not owner or not repo:
        return {"issues": []}
    
    try:
        issues = await drafter.fetch_issues(owner, repo, session_token)
        # Rank issues by beginner-friendliness using the graph
        graph = state.get("graph", {})
        ranked_issues = drafter.rank_issues(issues, graph)
        return {"issues": ranked_issues}
    except Exception as e:
        logger.error(f"Failed to fetch issues: {e}")
        return {"issues": [], "error": str(e)}


@app.post("/api/draft/qa")
async def contribution_qa_endpoint(req: ContributionQARequest, request: Request):
    """In-wizard Q&A: answers beginner questions about their contribution."""
    session_token = extract_token(request)
    if req.repo_url not in repo_cache:
        raise HTTPException(status_code=400, detail="Repository not analyzed yet.")
    
    state = repo_cache[req.repo_url]
    downloaded = state.get("downloaded_files", [])
    
    # Find relevant files for this contribution context
    relevant_contents = [f for f in downloaded if f["path"] in req.target_files]
    if not relevant_contents and downloaded:
        relevant_contents = downloaded[:5]
    
    result = await contribution_qa.answer(
        question=req.question,
        issue_title=req.issue_title,
        understanding=req.understanding,
        what_needs_to_change=req.what_needs_to_change,
        target_files=req.target_files,
        relevant_file_contents=relevant_contents,
        session_token=session_token
    )
    return result
