import httpx
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from config import GITHUB_TOKEN
from llm_key_pool import llm_key_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DraftPatch(BaseModel):
    issue_title: str
    target_file: str
    diff: str = Field(description="The drafted code patch (diff format or full file replacement).")
    test_code: str = Field(description="Drafted test case for the patch.")
    pr_description: str = Field(description="A detailed PR description explaining the fix.")

class ContributionDrafter:
    def __init__(self):
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Groundwork-Agent"
        }
        if GITHUB_TOKEN:
            self.headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    async def fetch_issues(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """Fetches issues labeled 'good first issue' or 'help wanted'."""
        issues = []
        for label in ["good first issue", "help wanted"]:
            url = f"https://api.github.com/repos/{owner}/{repo}/issues?state=open&labels={label.replace(' ', '%20')}"
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, headers=self.headers)
                if response.status_code == 200:
                    issues.extend(response.json())
                    
        # Remove pull requests (GitHub API returns PRs as issues)
        issues = [i for i in issues if "pull_request" not in i]
        return issues

    def rank_issues(self, issues: List[Dict[str, Any]], graph: Dict[str, Any]) -> Dict[str, Any]:
        """Ranks issues by tractability using graph out-degree (blast radius)."""
        if not issues:
            return None
            
        # Calculate file blast radius (how many files depend on this file)
        dependents_count = {f: 0 for f in graph.get("files", [])}
        
        for imp in graph.get("imports", []):
            src = imp.get("source")
            stmt = imp.get("statement", "")
            for target_file in graph.get("files", []):
                if target_file == src: continue
                target_base = target_file.split("/")[-1].split(".")[0]
                if target_base in stmt:
                    dependents_count[target_file] += 1
                    
        for call in graph.get("calls", []):
            caller = call.get("caller_file")
            callee_name = call.get("callee", "")
            for node in graph.get("nodes", []):
                if node.get("name") == callee_name:
                    callee_file = node.get("id", "").split(":")[0]
                    if caller and callee_file and caller != callee_file:
                        dependents_count[callee_file] += 1
                        
        def score_issue(issue):
            # Map issue to files if filename is in issue body/title
            text = (issue.get("title", "") + " " + (issue.get("body") or "")).lower()
            matched_files = [f for f in graph.get("files", []) if f.split("/")[-1].split(".")[0].lower() in text]
            
            if not matched_files:
                return 999999 # No known mapping, assume high risk/unknown
                
            # Average blast radius of implicated files (lower is better for beginners)
            return sum(dependents_count[f] for f in matched_files) / len(matched_files)
            
        issues.sort(key=score_issue)
        return issues[0]

    def draft_patch(self, issue: Dict[str, Any], graph: Dict[str, Any], downloaded_files: List[Dict[str, str]], session_token: str | None = None) -> DraftPatch:
        """Drafts a patch using the LLM. NEVER SUBMITS TO GITHUB."""
        logger.info(f"Drafting patch for issue: {issue['title']}")
        
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

Rules:
- Lines starting with `-` are removed
- Lines starting with `+` are added  
- Lines starting with ` ` (space) are context (unchanged)
- Every hunk MUST start with @@ -line,count +line,count @@
- Use actual line numbers from the file content provided
- DO NOT wrap the diff in markdown code fences
- DO NOT add any prose before or after the diff

DO NOT auto-submit. This is a local draft only.
"""),
            ("human", """Issue Title: {title}
Issue Body: {body}

Repository Context (Graph):
{graph_summary}

File Contents (Top files):
{files}

Draft the patch for the most relevant file using EXACTLY the unified diff format described above.
""")
        ])
        
        # Assemble context
        graph_summary = f"Total files: {len(graph.get('files', []))}, Total functions: {len(graph.get('nodes', []))}"
        
        # In a real system, we'd only pass files relevant to the issue.
        # Here we pass a small snippet of the first few files to fit context.
        file_snippets = ""
        for f in downloaded_files[:5]:
            file_snippets += f"\n--- {f['path']} ---\n{f['content'][:1000]}\n"
            
        llm = llm_key_pool.get_llm(session_token, temperature=0.2)
        structured_llm = llm.with_structured_output(DraftPatch)
        chain = prompt | structured_llm
        
        result: DraftPatch = chain.invoke({
            "title": issue["title"],
            "body": issue.get("body", "No description provided."),
            "graph_summary": graph_summary,
            "files": file_snippets
        })
        
        return result
