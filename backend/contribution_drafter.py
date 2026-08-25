import asyncio
import httpx
import logging
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from llm_key_pool import llm_key_pool
from key_pool import key_pool
from prompt_guard import sanitize_content

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class DraftPatch(BaseModel):
    """Legacy model — kept for backwards compatibility with /api/draft action path."""
    issue_title: str
    target_file: str
    diff: str = Field(description="The drafted code patch (diff format or full file replacement).")
    test_code: str = Field(description="Drafted test case for the patch.")
    pr_description: str = Field(description="A detailed PR description explaining the fix.")


class ContributionGuide(BaseModel):
    """Full guided contribution output — the core of the new Contribution Drafter."""
    issue_title: str = Field(description="Title of the GitHub issue being addressed.")
    issue_url: str = Field(description="Full URL to the GitHub issue.")
    difficulty: str = Field(description="One of: 'easy', 'medium', 'hard'")
    difficulty_reason: str = Field(description="One sentence explaining why this difficulty was assigned.")
    target_files: List[str] = Field(description="List of exact file paths that need to be changed.")
    understanding: str = Field(description="Plain English explanation of what this issue is about and why it exists. Written for a beginner.")
    what_needs_to_change: str = Field(description="Specific, concrete description of what code changes are needed and where.")
    diff: str = Field(description="Unified diff patch (--- a/file, +++ b/file format). If confidence is low, provide the closest best attempt with a comment.")
    test_code: str = Field(description="A test to verify the fix works. Can be empty string if not applicable.")
    pr_title: str = Field(description="Suggested PR title.")
    pr_description: str = Field(description="Complete PR description in markdown. Include: what the issue was, what changed, how to test.")
    confidence: str = Field(description="One of: 'high', 'partial', 'low'")
    confidence_reason: str = Field(description="If confidence is partial or low, explain exactly what's uncertain and what the user should investigate themselves.")


# ─────────────────────────────────────────────────────────────────────────────
# Difficulty scoring
# ─────────────────────────────────────────────────────────────────────────────

def score_issue_difficulty(issue: Dict[str, Any], graph: Dict[str, Any]) -> tuple[str, str, int]:
    """
    Returns (difficulty, reason, numeric_score).
    Hybrid: GitHub labels + blast radius + issue text heuristics.
    Lower numeric_score = better for beginners.
    """
    labels = [
        (l["name"] if isinstance(l, dict) else str(l)).lower()
        for l in issue.get("labels", [])
    ]
    title = (issue.get("title", "") or "").lower()
    body = (issue.get("body", "") or "").lower()
    text = title + " " + body

    score = 1000  # base score (lower = better for beginners)

    # GitHub label signals
    if any(l in labels for l in ["good first issue", "good-first-issue", "beginner", "starter", "easy"]):
        score -= 400
    if any(l in labels for l in ["help wanted", "help-wanted"]):
        score -= 200
    if any(l in labels for l in ["bug", "fix"]):
        score -= 100
    if any(l in labels for l in ["enhancement", "feature"]):
        score += 50
    if any(l in labels for l in ["complexity:high", "hard", "advanced", "complex"]):
        score += 500

    # Text heuristics
    easy_keywords = ["typo", "documentation", "readme", "comment", "spelling", "broken link", "update deps", "add test", "missing test"]
    hard_keywords = ["refactor", "architecture", "breaking change", "performance", "security", "race condition", "async", "concurrency", "memory leak"]
    
    for kw in easy_keywords:
        if kw in text:
            score -= 150
    for kw in hard_keywords:
        if kw in text:
            score += 200

    # Blast radius (how many files depend on the implicated files)
    dependents_count = {f: 0 for f in graph.get("files", [])}
    for imp in graph.get("imports", []):
        src = imp.get("source")
        stmt = imp.get("statement", "")
        for target_file in graph.get("files", []):
            if target_file == src:
                continue
            target_base = target_file.split("/")[-1].split(".")[0]
            if target_base in stmt:
                dependents_count[target_file] += 1

    matched_files = [f for f in graph.get("files", []) if f.split("/")[-1].split(".")[0].lower() in text]
    if matched_files:
        avg_blast = sum(dependents_count.get(f, 0) for f in matched_files) / len(matched_files)
        score += int(avg_blast * 10)

    # Classify
    if score < 700:
        return "easy", "Labeled or described as a beginner-friendly task with low blast radius.", score
    elif score < 1200:
        return "medium", "Moderate complexity — requires understanding the codebase but changes are contained.", score
    else:
        return "hard", "High complexity — large blast radius, complex logic, or architectural changes needed.", score


def find_relevant_files(issue: Dict[str, Any], graph: Dict[str, Any], downloaded_files: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Given an issue, find which files are most likely relevant by:
    1. Extracting keywords (filenames, function names, error messages) from the issue text
    2. Matching them against the graph's nodes, files, and imports
    3. Returning the actual file contents of those matches
    """
    title = issue.get("title", "") or ""
    body = issue.get("body", "") or ""
    text = (title + " " + body).lower()

    # Extract potential file/module names from the issue text
    # Look for patterns like: file.py, SomeClass, someFunction, /path/to/file
    potential_refs = set()
    
    # Explicit file name references
    file_matches = re.findall(r'\b[\w/-]+\.[a-zA-Z]{1,5}\b', text)
    for m in file_matches:
        potential_refs.add(m.lower().split("/")[-1].split(".")[0])
    
    # CamelCase identifiers (likely class/function names)
    camel_matches = re.findall(r'\b[A-Z][a-zA-Z0-9]{2,}\b', title + " " + body)
    for m in camel_matches:
        potential_refs.add(m.lower())
    
    # snake_case identifiers
    snake_matches = re.findall(r'\b[a-z][a-z0-9_]{3,}\b', text)
    for m in snake_matches:
        potential_refs.add(m)

    # Score each file by how many keywords it matches
    file_scores: Dict[str, int] = {}
    
    for f in graph.get("files", []):
        file_base = f.split("/")[-1].split(".")[0].lower()
        score = 0
        
        # Direct filename match in issue text
        if file_base in text:
            score += 100
        
        # Keyword partial match
        for ref in potential_refs:
            if ref in file_base or file_base in ref:
                score += 30
        
        # Functions in this file mentioned in issue
        for node in graph.get("nodes", []):
            if node.get("id", "").startswith(f + ":"):
                func_name = node.get("name", "").lower()
                if func_name in text or func_name in potential_refs:
                    score += 50
        
        if score > 0:
            file_scores[f] = score

    # Sort by score, take top 10 relevant files
    top_relevant = sorted(file_scores.items(), key=lambda x: x[1], reverse=True)[:10]
    relevant_paths = {f for f, _ in top_relevant}

    # Return actual file contents for relevant files
    result = [f for f in downloaded_files if f["path"] in relevant_paths]
    
    # Fallback: if nothing matched, return the 5 most central files
    if not result and downloaded_files:
        result = downloaded_files[:5]
    
    logger.info(f"Issue-targeted file discovery: found {len(result)} relevant files for issue '{issue.get('title', '')[:50]}'")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main class
# ─────────────────────────────────────────────────────────────────────────────

class ContributionDrafter:
    def __init__(self):
        pass

    async def fetch_issues(self, owner: str, repo: str, session_token: str | None = None) -> List[Dict[str, Any]]:
        """Fetches all open issues (up to 100), enriched with metadata."""
        issues = []
        url = f"https://api.github.com/repos/{owner}/{repo}/issues?state=open&per_page=100&sort=created&direction=desc"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Groundwork-Agent"
        }
        token = session_token or key_pool.get_best_key()
        if token:
            headers["Authorization"] = f"Bearer {token}"
            
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                issues.extend(response.json())
                
        # Remove pull requests (GitHub API returns PRs as issues)
        issues = [i for i in issues if "pull_request" not in i]
        
        # Enrich with normalized label list
        for issue in issues:
            issue["labels"] = [
                (l["name"] if isinstance(l, dict) else str(l))
                for l in issue.get("labels", [])
            ]
            issue["author"] = issue.get("user", {}).get("login", "unknown")
        
        return issues

    def rank_issues(self, issues: List[Dict[str, Any]], graph: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Ranks issues from most to least beginner-friendly.
        Returns the full list with difficulty metadata attached.
        """
        if not issues:
            return []
        
        scored = []
        for issue in issues:
            difficulty, reason, score = score_issue_difficulty(issue, graph)
            issue["_difficulty"] = difficulty
            issue["_difficulty_reason"] = reason
            issue["_score"] = score
            scored.append(issue)
        
        scored.sort(key=lambda i: i["_score"])
        return scored

    async def draft_contribution_guide(
        self,
        issue: Dict[str, Any],
        graph: Dict[str, Any],
        downloaded_files: List[Dict[str, str]],
        owner: str,
        repo: str,
        session_token: str | None = None
    ) -> ContributionGuide:
        """
        Generates a full ContributionGuide for a selected issue.
        Uses issue-targeted file discovery to pass only the RELEVANT files to the LLM.
        """
        logger.info(f"Drafting contribution guide for: {issue.get('title', '')[:60]}")
        
        # Issue-targeted file discovery — NOT random top-5
        relevant_files = find_relevant_files(issue, graph, downloaded_files)
        
        # Build file snippets (more content = better LLM output)
        file_snippets = ""
        for f in relevant_files[:8]:
            file_snippets += f"\n--- {f['path']} ---\n"
            # Sanitize file content before injecting into the LLM prompt
            file_snippets += sanitize_content(f["content"][:3000])
        
        # Build graph summary for the LLM
        graph_summary = {
            "total_files": len(graph.get("files", [])),
            "total_functions": graph.get("total_public_functions", len(graph.get("nodes", []))),
            "relevant_files_found": [f["path"] for f in relevant_files],
            "entry_points": [ep.get("id", "") for ep in graph.get("entry_points", [])][:10],
        }

        difficulty = issue.get("_difficulty", "medium")
        difficulty_reason = issue.get("_difficulty_reason", "Estimated based on issue content.")
        issue_url = issue.get("html_url", f"https://github.com/{owner}/{repo}/issues/{issue.get('number', '')}")

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert open-source mentor helping a complete beginner make their first contribution.

Your output must be:
1. HONEST: If you're not sure what code to change, say so in confidence_reason.
2. BEGINNER-FRIENDLY: The `understanding` and `what_needs_to_change` fields must be written so a 16-year-old who can code basic Python could understand them.
3. SPECIFIC: Always cite exact file paths and function names when you know them.
4. PRACTICAL: The `diff` must be a real, syntactically valid unified diff.

For the `diff` field:
- Use standard unified diff format:
  --- a/path/to/file.py
  +++ b/path/to/file.py
  @@ -10,7 +10,8 @@
   context_line
  -removed_line
  +added_line
- DO NOT wrap in markdown fences inside the JSON field.
- If you don't have enough context to write a perfect diff, provide your best-effort valid unified diff anyway (especially for simple additions like exports or imports). Only use "# Unable to generate patch" if it is completely impossible to guess.
- confidence: 'high' = you are certain the diff is correct
- confidence: 'partial' = the diff is directionally right but may need adjustment  
- confidence: 'low' = you can identify WHERE to look but cannot write the actual code
"""),
            ("human", """GitHub Issue:
Title: {issue_title}
Number: #{issue_number}
Labels: {labels}
Body:
{issue_body}

Repository: {owner}/{repo}
Graph Summary: {graph_summary}

Relevant file contents (these are the files most likely to need changes):
{file_snippets}

Generate a complete ContributionGuide. Be honest about what you know and don't know.
""")
        ])

        llm = llm_key_pool.get_llm(session_token, temperature=0.2)
        structured_llm = llm.with_structured_output(ContributionGuide)
        chain = prompt | structured_llm

        max_retries = 6
        backoff = 2.0
        
        for attempt in range(1, max_retries + 1):
            try:
                result: ContributionGuide = chain.invoke({
                    "issue_title": issue.get("title", ""),
                    "issue_number": issue.get("number", ""),
                    "labels": ", ".join(issue.get("labels", [])),
                    "issue_body": (issue.get("body", "") or "No description provided.")[:3000],
                    "owner": owner,
                    "repo": repo,
                    "graph_summary": str(graph_summary),
                    "file_snippets": file_snippets or "No relevant files found in the analyzed codebase.",
                })
                # Attach metadata computed before LLM call
                result.difficulty = difficulty
                result.difficulty_reason = difficulty_reason
                result.issue_url = issue_url
                return result
            except Exception as e:
                logger.warning(f"ContributionGuide attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error("All retries exhausted for contribution guide.")
                    return ContributionGuide(
                        issue_title=issue.get("title", "Unknown Issue"),
                        issue_url=issue_url,
                        difficulty=difficulty,
                        difficulty_reason=difficulty_reason,
                        target_files=[f["path"] for f in relevant_files[:3]],
                        understanding="I was unable to generate a full guide due to AI service rate limits. Please try again.",
                        what_needs_to_change="Please try again in a moment.",
                        diff="# AI service unavailable. Please retry.",
                        test_code="",
                        pr_title=f"Fix: {issue.get('title', '')}",
                        pr_description=f"Fixes #{issue.get('number', '')}",
                        confidence="low",
                        confidence_reason="AI service was unavailable during generation. The file discovery above is still valid — check those files for the fix."
                    )
                import asyncio
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

    async def draft_patch(self, issue: Dict[str, Any], graph: Dict[str, Any], downloaded_files: List[Dict[str, str]], session_token: str | None = None) -> DraftPatch:
        """
        Legacy method kept for backwards compatibility with /api/draft action path.
        Now uses issue-targeted file discovery instead of random top-5.
        """
        logger.info(f"Drafting patch for issue: {issue.get('title', '')}")
        
        # Use targeted file discovery
        relevant_files = find_relevant_files(issue, graph, downloaded_files)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a senior developer helping a junior contributor draft a PR.
Read the issue description, analyze the provided codebase context, and draft a patch, a test, and a PR description.

CRITICAL INSTRUCTION FOR DIFF FIELD:
The `diff` field MUST be a syntactically valid unified diff patch. No prose. No explanations. Only diff lines.

REQUIRED FORMAT (copy this structure exactly):
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -10,7 +10,8 @@
 def existing_function():
-    old_line = True
+    new_line = True
+    added_line = True
     return result

Rules for the `diff` field:
- Lines starting with `-` are removed
- Lines starting with `+` are added  
- Lines starting with ` ` (space) are context (unchanged)
- Every hunk MUST start with @@ -line,count +line,count @@
- Use actual line numbers from the file content provided
- DO NOT wrap the diff in markdown code fences inside the JSON field
- DO NOT add any prose before or after the diff inside the JSON field

DO NOT auto-submit. This is a local draft only.
"""),
            ("human", """Issue Title: {title}
Issue Body: {body}

Repository Context:
{graph_summary}

Relevant File Contents:
{files}

Provide the patch, test code, and PR description.
""")
        ])
        
        graph_summary = f"Total files: {len(graph.get('files', []))}, Total functions: {graph.get('total_public_functions', len(graph.get('nodes', [])))}"
        file_snippets = ""
        for f in relevant_files[:6]:
            file_snippets += f"\n--- {f['path']} ---\n{f['content'][:2000]}\n"

        max_retries = 6
        backoff = 2.0
        for attempt in range(1, max_retries + 1):
            try:
                llm = llm_key_pool.get_llm(session_token, temperature=0.2)
                structured_llm = llm.with_structured_output(DraftPatch)
                chain = prompt | structured_llm
                result: DraftPatch = chain.invoke({
                    "title": issue.get("title", ""),
                    "body": issue.get("body", "No description provided."),
                    "graph_summary": graph_summary,
                    "files": file_snippets
                })
                return result
            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "rate limit" in error_str or "quota" in error_str:
                    llm_key_pool.mark_rate_limit_for_llm(llm)
                logger.warning(f"draft_patch attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error("All draft_patch retries exhausted.")
                    raise
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)
