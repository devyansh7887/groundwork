import os
import json
import logging
from typing import Dict, Any, List, Optional
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
        
    def _calculate_centrality(self, graph: Dict[str, Any]) -> List[str]:
        """Returns top 5 files by highest centrality (using NetworkX PageRank)."""
        import networkx as nx
        
        G = nx.DiGraph()
        
        # Add all files as nodes
        for f in graph.get("files", []):
            G.add_node(f)
            
        # Add import edges (importer -> imported module)
        for imp in graph.get("imports", []):
            src = imp.get("source")
            stmt = imp.get("statement", "")
            for target_file in graph.get("files", []):
                if target_file == src:
                    continue
                target_base = target_file.split("/")[-1].split(".")[0]
                if target_base in stmt:
                    G.add_edge(src, target_file)
                    
        # Add call edges (caller_file -> callee_file)
        for call in graph.get("calls", []):
            caller = call.get("caller_file")
            callee_name = call.get("callee", "")
            for node in graph.get("nodes", []):
                if node.get("name") == callee_name:
                    callee_file = node.get("id", "").split(":")[0]
                    if caller and callee_file and caller != callee_file:
                        G.add_edge(caller, callee_file)
                        
        if len(G.nodes) == 0:
            return []
            
        try:
            # Calculate PageRank
            pr = nx.pagerank(G)
            sorted_files = sorted(pr.items(), key=lambda x: x[1], reverse=True)
            return [f[0] for f in sorted_files[:3]]
        except Exception as e:
            logger.error(f"PageRank calculation failed: {e}")
            return graph.get("files", [])[:5]
        
    def synthesize(self, graph: Dict[str, Any], downloaded_files: List[Dict[str, str]], verifier_feedback: str = "", mode: str = "technical", session_token: str | None = None) -> Dict[str, Any]:
        """Generates the narrative and claims list from the graph and file contents.
        
        Args:
            graph: The Cartographer's static analysis graph (ground truth).
            downloaded_files: Raw file contents for snippet grounding.
            verifier_feedback: Non-empty string on retry runs. Contains the Verifier's
                               structured rejection report.
            mode: 'technical', 'eli5', or 'tldr'
        """
        
        # 1. Identify entry points and highest centrality files
        entry_point_files = set(ep.get("id", "").split(":")[0] for ep in graph.get("entry_points", []))
        central_files = set(self._calculate_centrality(graph))
        
        important_files = entry_point_files.union(central_files)
        
        # 2. Gather contents for important files
        file_contents = ""
        for f in downloaded_files:
            if f["path"] in important_files:
                file_contents += f"\n--- File: {f['path']} ---\n"
                # Truncate content to avoid blowing up context for Groq limits
                file_contents += f["content"][:300] 
                
        # 3. Build prompt messages — base turn is always present.
        #    On retries, a corrective second human turn is appended so the model
        #    knows exactly which claims failed verification and must be fixed.
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
            ("human", """Here is the static analysis graph of the repository:
{graph_json}

Here are the contents of the entry points and highest-centrality files:
{file_contents}

Produce the structured output with claims and narrative text.
"""),
        ]

        if verifier_feedback:
            # Corrective turn: show the model its previous failures and instruct it
            # to replace each failing claim with one that IS in the graph.
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
        
        # Simplify graph for token usage to respect Groq limits
        simplified_graph = {
            "files": graph["files"][:50],
            "nodes": [n.get("id") for n in graph["nodes"]][:10],
            "entry_points": [ep.get("id") for ep in graph["entry_points"]][:10],
            "calls": graph["calls"][:10],
        }
        invoke_kwargs: Dict[str, Any] = {
            "graph_json": json.dumps(simplified_graph, indent=2),
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
                import time
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Synthesizer attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error("All retries exhausted for synthesizer. Returning fallback.")
                    return {
                        "claims": [],
                        "narrative": "⚠️ **Analysis Unavailable**: The AI models are currently experiencing heavy load or rate limits. Please try again later or provide a custom API token."
                    }
                time.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

