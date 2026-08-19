import os
import json
import time
import logging
from typing import Dict, Any, List, Optional
from collections import Counter
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from llm_key_pool import llm_key_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Claim(BaseModel):
    claim: str = Field(description="A specific architectural or data-flow claim.")
    cited_file: str = Field(description="The exact file path cited for this claim.")
    cited_symbol: Optional[str] = Field(None, description="The specific function or class cited.")

class SynthesizerOutput(BaseModel):
    claims: List[Claim] = Field(description="Structured list of architectural claims with citations.")
    narrative: str = Field(description="Narrative text for a README (overview, key entry points, data flow description). Must cite files.")

class Synthesizer:
    def __init__(self):
        pass
        
    def _build_intelligence_summary(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a rich, ranked intelligence summary to send to the LLM.
        Instead of sending 10 random nodes, we send the most architecturally
        significant data: most-called functions, most-imported modules, entry points.
        """
        # 1. Rank functions by how often they appear as call targets (centrality)
        call_targets = Counter()
        for call in graph.get("calls", []):
            callee = call.get("callee", "")
            if callee:
                call_targets[callee] += 1
        
        # Top 30 most-called functions with their locations
        top_nodes_by_freq = []
        seen_names = set()
        for callee_name, freq in call_targets.most_common(50):
            if len(top_nodes_by_freq) >= 30:
                break
            # Find which file this function is in
            for node in graph.get("nodes", []):
                if node.get("name") == callee_name and callee_name not in seen_names:
                    top_nodes_by_freq.append({
                        "id": node["id"],
                        "name": callee_name,
                        "call_count": freq,
                        "type": node.get("type", "function")
                    })
                    seen_names.add(callee_name)
                    break
        
        # 2. Most imported modules (architectural dependencies)
        import_counts = Counter()
        for imp in graph.get("imports", []):
            mod = imp.get("target_module", "")
            if mod and not mod.startswith("."):  # skip relative imports for this summary
                import_counts[mod] += 1
        top_imports = [{"module": mod, "import_count": cnt} for mod, cnt in import_counts.most_common(20)]

        # 3. All entry points (unlimited — these are the architectural spine)
        all_entry_points = list(set(ep.get("id", "") for ep in graph.get("entry_points", [])))

        # 4. File list (up to 100)
        all_files = graph.get("files", [])[:100]

        return {
            "total_files": len(graph.get("files", [])),
            "files_sample": all_files,
            "top_functions_by_call_frequency": top_nodes_by_freq,
            "top_imported_modules": top_imports,
            "entry_points": all_entry_points[:15],
            "total_nodes": len(graph.get("nodes", [])),
            "total_calls": len(graph.get("calls", [])),
            "total_imports": len(graph.get("imports", [])),
            # Graph stats (accurate, from full file content)
            "total_sloc": graph.get("total_sloc", 0),
            "total_public_functions": graph.get("total_public_functions", 0),
        }
        
    def synthesize(self, graph: Dict[str, Any], downloaded_files: List[Dict[str, str]], verifier_feedback: str = "", mode: str = "technical", session_token: str | None = None) -> Dict[str, Any]:
        """Generates the narrative and claims list from the graph and file contents."""
        
        # 1. Build intelligence summary (ranked, not random)
        intel = self._build_intelligence_summary(graph)
        
        # 2. Identify entry points and highest centrality files
        entry_point_files = set(ep.split(":")[0] for ep in intel["entry_points"] if ":" in ep)
        
        # Top 5 files by call centrality
        central_files = set()
        for node_info in intel["top_functions_by_call_frequency"][:5]:
            fpath = node_info["id"].split(":")[0] if ":" in node_info["id"] else ""
            if fpath:
                central_files.add(fpath)
        
        important_files = list(entry_point_files.union(central_files))[:8] # Cap to 8 files max to prevent token limits
        
        # 3. Gather contents for important files — 1500 chars each
        file_contents = ""
        for f in downloaded_files:
            if f["path"] in important_files:
                file_contents += f"\n--- File: {f['path']} ---\n"
                file_contents += f["content"][:1500]  # 1500 chars = meaningful context
                
        mode_prompts = {
            "technical": """You are a senior software architect writing an internal ADR (Architecture Decision Record) for other senior engineers.
Write with precision. Use exact technical terms: design patterns (MVC, Repository, Mediator, CQRS), protocol names (REST, gRPC, SSE), runtime concepts (event loop, coroutine, GIL), and framework internals.
Structure your narrative as:
## Overview (2-3 sentences: tech stack + primary purpose)
## Entry Points (exact files/functions that bootstrap the system)
## Data Flow (step-by-step request lifecycle with file citations)
## Key Abstractions (the 3-5 most important classes/modules and why they exist)
## Dependency Architecture (how modules import each other, where coupling is tight)
Be dense, specific, and technical. Every claim must cite a real file.""",

            "eli5": """You are a patient, friendly teacher explaining this codebase to a 16-year-old who knows basic Python but has never built a real project.
Use everyday analogies. Examples:
- A Router is like a receptionist who sends visitors to the right department
- A database is like a filing cabinet
- An API is like a restaurant menu — you order (request), the kitchen makes it (server), you get food (response)
- Async/await is like ordering coffee and sitting down to do other work while you wait

Structure your narrative as:
## What Does This App Actually Do? (1 paragraph, plain English, no jargon)
## The Main Characters (key files/modules as personality descriptions — "This file is the boss of...")
## How a Request Travels Through the App (a story: "When you click the button, here's what happens...")
## The Smartest Parts (2-3 clever design choices, explained simply)

IMPORTANT: Never use words like "middleware", "abstraction", "instantiation", "singleton" without immediately explaining them with an analogy. Make it feel like a story, not documentation.""",

            "tldr": """You are an executive assistant briefing a busy CTO who has 90 seconds.
Write a punchy, information-dense summary. Format as:

## TLDR — {repo name} in 90 seconds

**What it is:** [One sentence. What problem does this solve?]
**Stack:** [Technology keywords only: Python, FastAPI, LangChain, React, etc.]
**Scale:** [Files, functions, complexity — just numbers]
**Architecture pattern:** [e.g. "Pipeline + LangGraph graph execution", "REST API + React SPA", "MCP server"]

## Key Files (Top 5)
| File | Role |
|------|------|
| file.py | What it does in 5 words |

## Architecture in 5 Bullets
- Bullet 1
- Bullet 2
...

## Watch Out For
[1-2 notable complexities or risks visible in the code]

Be ruthlessly brief. No filler sentences. Every word must earn its place."""
        }
        system_persona = mode_prompts.get(mode, mode_prompts["technical"])

        messages = [
            ("system", f"""{system_persona}
Your job is to analyze a codebase's static analysis graph and key file contents, and output two things:
1. A descriptive narrative (Overview, Key Entry Points, Data Flow). Use very clear markdown formatting (H1, H2, H3, bullet points) to separate sections.
2. A structured list of verifiable claims.

CRITICAL RULES:
- EVERY factual claim you make in the narrative MUST be accompanied by a file citation.
- Do not invent or guess any architecture. Rely STRICTLY on the provided graph and file contents.
- In your structured claims list, `cited_file` must be exactly the file path from the repository.
- If you cannot verify a claim from the provided data, do not include it.
"""),
            ("human", """Here is the ranked intelligence summary of the repository:
{graph_json}

Here are the contents of the entry points and highest-centrality files:
{file_contents}

Produce the structured output with claims and narrative text.
"""),
        ]

        if verifier_feedback:
            messages.append(
                ("human", """A downstream Verifier agent reviewed your previous output and rejected the following claims.
You MUST fix every issue listed below before producing your corrected output.
Do NOT re-emit any claim that the Verifier marked Unverified unless you change the cited_file
to one that actually exists in the graph above.

--- VERIFIER REJECTION REPORT ---
{verifier_feedback}
---------------------------------

Now produce a corrected structured output. Only include claims you are certain can be
verified against the graph and file contents above.""")
            )

        prompt = ChatPromptTemplate.from_messages(messages)
        
        invoke_kwargs: Dict[str, Any] = {
            "graph_json": json.dumps(intel, indent=2),
            "file_contents": file_contents,
        }
        if verifier_feedback:
            invoke_kwargs["verifier_feedback"] = verifier_feedback
            logger.info("Synthesizer retry — injecting Verifier feedback into prompt.")
        else:
            logger.info("Calling Synthesizer for initial architecture pass...")

        max_retries = 3
        backoff = 2.0
        
        for attempt in range(1, max_retries + 1):
            try:
                llm = llm_key_pool.get_llm(session_token, temperature=0.1)
                structured_llm = llm.with_structured_output(SynthesizerOutput)
                chain = prompt | structured_llm
                result: SynthesizerOutput = chain.invoke(invoke_kwargs)
                return {
                    "claims": [c.model_dump() for c in result.claims],
                    "narrative": result.narrative
                }
            except Exception as e:
                error_str = str(e).lower()
                # If we hit a rate limit, quota issue, or 429, mark the token so the next attempt uses a new key
                if "429" in error_str or "rate limit" in error_str or "quota" in error_str or "exhausted" in error_str:
                    if hasattr(llm, "token_used"):
                        llm_key_pool.mark_rate_limit(llm.token_used, retry_after=60)
                
                logger.warning(f"Synthesizer attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error("All retries exhausted for synthesizer. Returning fallback.")
                    return {
                        "claims": [],
                        "narrative": f"⚠️ **Analysis Unavailable**: {str(e)} (Attempted {max_retries} times. Please provide a custom API token or wait for rate limits to reset.)"
                    }
                time.sleep(backoff)
                backoff = min(backoff * 2, 10.0)
