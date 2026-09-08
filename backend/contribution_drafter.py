import asyncio
import httpx
import logging
import re
import json
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_core.tools import tool
from llm_key_pool import llm_key_pool
from key_pool import key_pool
from prompt_guard import sanitize_content
from cost_tracker import track

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

class ResearchRequest(BaseModel):
    required_files: List[str] = Field(description="Exact file paths from the repository needed to write the code and tests. Must include the core files, definitions, and their corresponding test files.")
    reasoning: str = Field(description="Why these files are needed.")


class FileModification(BaseModel):
    file_path: str = Field(description="The exact path to the file that needs to be changed.")
    where_to_put_it: str = Field(description="Clear instructions on exactly where inside the file this change goes (e.g., 'Inside the parse() function, right after line 45').")
    what_to_remove: str = Field(description="The exact code that should be deleted or replaced. Leave empty if you are only adding new code.")
    what_to_add: str = Field(description="The exact new code that the user needs to copy and paste into the file.")

class ContributionGuide(BaseModel):
    """Full guided contribution output — the core of the new Contribution Drafter."""
    issue_title: str = Field(description="Title of the GitHub issue being addressed.")
    issue_url: str = Field(description="Full URL to the GitHub issue.")
    difficulty: str = Field(description="One of: 'easy', 'medium', 'hard'")
    difficulty_reason: str = Field(description="One sentence explaining why this difficulty was assigned.")
    target_files: List[str] = Field(description="List of exact file paths that need to be changed.")
    understanding: str = Field(description="Plain English explanation of what this issue is about and why it exists. Written for a beginner.")
    modifications: List[FileModification] = Field(description="A list of specific file modifications required to fix the issue. This completely replaces the old step-by-step tutorial format with strict, actionable code blocks.")
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
        branch: str = "main",
        session_token: str | None = None
    ) -> ContributionGuide:
        """
        Generates a full ContributionGuide for a selected issue.
        Uses an Agentic Loop to explore the codebase before writing the patch.
        """
        logger.info(f"Agentic Draft started for: {issue.get('title', '')[:60]}")
        
        difficulty = issue.get("_difficulty", "medium")
        difficulty_reason = issue.get("_difficulty_reason", "Estimated based on issue content.")
        issue_url = f"https://github.com/{owner}/{repo}/issues/{issue.get('number', '')}"
        
        downloaded_map = {f["path"]: f for f in downloaded_files}
        all_repo_files = graph.get("files", [])
        
        # We need an httpx client for dynamically reading files during the loop
        client = httpx.AsyncClient(timeout=10.0)

        # ─── Tools for the Agent ───
        def search_codebase(query: str) -> str:
            """
            Search the repository files for a string or regex. Use this to find where a variable, function, or string is defined or used.
            Returns a list of matching lines with their file paths.
            """
            results = []
            logger.info(f"Agent searching codebase for: {query}")
            for file_path, file_data in downloaded_map.items():
                content = file_data.get("content", "")
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    if query.lower() in line.lower():
                        results.append(f"{file_path}:{i+1}: {line.strip()}")
            
            # Also check file names if we didn't find much in downloaded files
            if not results:
                for f in all_repo_files:
                    if query.lower() in f.lower():
                        results.append(f"File match: {f}")

            if not results:
                return f"No results found for '{query}' in downloaded context."
            
            return "\n".join(results[:50]) + ("\n...(truncated)" if len(results) > 50 else "")

        async def read_file(path: str) -> str:
            """
            Read the full contents of a file from the repository. Use this to inspect the implementation of a file you found via search.
            """
            logger.info(f"Agent reading file: {path}")
            # Try to resolve fuzzy match
            resolved_path = None
            if path in all_repo_files:
                resolved_path = path
            else:
                for p in all_repo_files:
                    if p.endswith(path) or path.endswith(p):
                        resolved_path = p
                        break
            
            if not resolved_path:
                return f"File '{path}' not found in repository."
                
            if resolved_path in downloaded_map:
                return sanitize_content(downloaded_map[resolved_path]["content"][:15000])
                
            # Dynamic fetch from GitHub if it wasn't pre-downloaded
            try:
                url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{resolved_path}"
                res = await client.get(url)
                res.raise_for_status()
                content = res.text
                downloaded_map[resolved_path] = {"path": resolved_path, "content": content}
                return sanitize_content(content[:15000])
            except Exception as e:
                return f"Failed to fetch {resolved_path}: {str(e)}"

        # We wrap these in a dict so we can invoke them dynamically
        tools_map = {
            "search_codebase": search_codebase,
            "read_file": read_file
        }
        
        # Pydantic schema for the final output tool
        class SubmitContributionGuide(BaseModel):
            """Submit the final guide once you have fully explored the codebase and have high confidence in your patch."""
            guide: ContributionGuide

        # ─── System Prompt ───
        system_prompt = f"""You are an autonomous expert open-source contributor. Your task is to fix a GitHub issue.
You must ACTUALLY SOLVE the problem. Do NOT guess the answer if you don't know the exact file paths and edge cases.
You have tools to `search_codebase` and `read_file`. Use them repeatedly to explore the codebase.
For example, if the issue mentions "disconnected backends", you MUST search the codebase for "backend" or "disconnected" and read those files to understand the architecture BEFORE writing your patch.

Once you have investigated and are 100% ready, call `SubmitContributionGuide` to provide the final patch and explanation.

Repository: {owner}/{repo}
Total files in repo: {len(all_repo_files)}

CRITICAL RULES FOR FINAL PATCH:
1. The `diff` MUST be a real, syntactically valid unified diff using `--- a/file` and `+++ b/file` headers.
2. If you cannot find the solution after exploring, be honest and mark confidence as 'low'.
"""

        issue_body = (issue.get("body", "") or "No description provided.")[:3000]
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Issue #{issue.get('number', '')}: {issue.get('title', '')}\n\n{issue_body}\n\nPlease explore the codebase and then submit the final ContributionGuide.")
        ]

        llm = llm_key_pool.get_llm(session_token, temperature=0.1)
        
        # Bind the tools and the forced output schema
        search_tool = StructuredTool.from_function(
            func=search_codebase,
            name="search_codebase",
            description="Search the repository files for a string."
        )
        def read_file_sync(path: str) -> str:
            # Try to resolve fuzzy match
            resolved_path = None
            if path in all_repo_files:
                resolved_path = path
            else:
                for p in all_repo_files:
                    if p.endswith(path) or path.endswith(p):
                        resolved_path = p
                        break
            
            if not resolved_path:
                return f"File '{path}' not found in repository."
                
            if resolved_path in downloaded_map:
                return sanitize_content(downloaded_map[resolved_path]["content"][:15000])
            return f"File '{resolved_path}' not in pre-downloaded context. Use search_codebase first."

        read_tool = StructuredTool.from_function(
            func=read_file_sync,
            name="read_file",
            description="Read the full contents of a file from the repository."
        )
        
        llm_with_tools = llm.bind_tools([search_tool, read_tool, SubmitContributionGuide])

        max_iterations = 8
        final_guide = None
        
        try:
            for i in range(max_iterations):
                logger.info(f"Agent iteration {i+1}/{max_iterations}")
                with track("contribution_drafter", "groq"):
                    response = await llm_with_tools.ainvoke(messages)
                messages.append(response)

                if not response.tool_calls:
                    # LLM didn't call a tool. Prompt it to submit.
                    messages.append(HumanMessage(content="Please call a tool to continue exploring, or call SubmitContributionGuide if you are finished."))
                    continue
                
                # Execute tool calls
                for tool_call in response.tool_calls:
                    name = tool_call["name"]
                    args = tool_call["args"]
                    
                    if name == "SubmitContributionGuide":
                        logger.info("Agent submitted the final ContributionGuide.")
                        final_guide = ContributionGuide(**args["guide"])
                        break
                    
                    elif name == "search_codebase":
                        result = search_codebase(**args)
                        messages.append(ToolMessage(tool_call_id=tool_call["id"], content=result))
                        
                    elif name == "read_file":
                        result = await read_file(**args)
                        messages.append(ToolMessage(tool_call_id=tool_call["id"], content=result))
                        
                if final_guide:
                    break
        except Exception as e:
            logger.error(f"Agent loop crashed: {e}")
            
        await client.aclose()
        
        if final_guide:
            final_guide.difficulty = difficulty
            final_guide.difficulty_reason = difficulty_reason
            final_guide.issue_url = issue_url
            return final_guide
            
        # Fallback if agent failed or ran out of iterations
        logger.error("Agent exhausted iterations without submitting a guide.")
        return ContributionGuide(
            issue_title=issue.get("title", "Unknown Issue"),
            issue_url=issue_url,
            difficulty=difficulty,
            difficulty_reason=difficulty_reason,
            target_files=[],
            understanding="I was unable to fully explore the codebase within the time limit. Please review manually.",
            modifications=[],
            diff="# Agent exhausted iterations",
            test_code="",
            pr_title=f"Fix: {issue.get('title', '')}",
            pr_description="Draft failed.",
            confidence="low",
            confidence_reason="Agent exhausted max iterations."
        )

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
                    llm_key_pool.mark_rate_limit_for_llm(llm, error_str=str(e))
                logger.warning(f"draft_patch attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error("All draft_patch retries exhausted.")
                    raise
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

