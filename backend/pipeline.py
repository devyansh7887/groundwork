import asyncio
import logging
from typing import Dict, Any, List, TypedDict
from langgraph.graph import StateGraph, END
from ingestor import Ingestor
from cartographer import Cartographer
from git_blame import GitBlameAnalyzer
from synthesizer import Synthesizer
from diagram_agent import DiagramAgent
from verifier import Verifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PipelineState(TypedDict):
    repo_url: str
    repo_metadata: Dict[str, Any]
    downloaded_files: List[Dict[str, str]]
    graph: Dict[str, Any]
    claims: List[Dict[str, Any]]
    narrative: str
    mermaid_diagram: str
    readme_content: str
    synthesis_retries: int
    verifier_feedback: str
    session_token: str
    mode: str
    security_findings: List[Dict[str, Any]]
    pattern_findings: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]

class Pipeline:
    def __init__(self):
        self.ingestor = Ingestor()
        self.cartographer = Cartographer()
        self.synthesizer = Synthesizer()
        self.diagram_agent = DiagramAgent()
        self.verifier = Verifier()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(PipelineState)
        
        workflow.add_node("ingest", self.node_ingest)
        workflow.add_node("cartograph", self.node_cartograph)
        workflow.add_node("synthesize", self.node_synthesize)
        workflow.add_node("verify", self.node_verify)
        workflow.add_node("diagram", self.node_diagram)
        workflow.add_node("write_readme", self.node_write_readme)
        
        workflow.set_entry_point("ingest")
        workflow.add_edge("ingest", "cartograph")
        workflow.add_edge("cartograph", "synthesize")
        workflow.add_edge("synthesize", "verify")
        
        # Conditional edge from verify
        workflow.add_conditional_edges(
            "verify",
            self.route_after_verify,
            {
                "retry": "synthesize",
                "continue": "diagram"
            }
        )
        
        workflow.add_edge("diagram", "write_readme")
        workflow.add_edge("write_readme", END)
        
        return workflow.compile()
        
    async def node_ingest(self, state: PipelineState):
        logger.info("🔍  Connecting to GitHub and reading repository...")
        
        # Instantiate Ingestor per request to use session_token if provided
        ingestor = Ingestor(state.get("session_token"))
        repo_data = await ingestor.ingest_repository(state["repo_url"])
        
        files_to_download = repo_data["files"]
        downloaded = []
        
        sem = asyncio.Semaphore(5) # Max 5 concurrent downloads to respect API rate limits and avoid ConnectTimeout
        
        completed_downloads = 0
        total_downloads = len(files_to_download)
        
        async def fetch_file(file_info):
            nonlocal completed_downloads
            async with sem:
                content = await ingestor.fetch_file_content(
                    repo_data["owner"], 
                    repo_data["repo"], 
                    repo_data["branch"], 
                    file_info["path"]
                )
                completed_downloads += 1
                if completed_downloads % max(1, total_downloads // 10) == 0 or completed_downloads == total_downloads:
                    logger.info(f"📥 Fetching file {completed_downloads}/{total_downloads}...")
                return {"path": file_info["path"], "content": content}
                
        tasks = [fetch_file(f) for f in files_to_download]
        results = await asyncio.gather(*tasks)
        downloaded = [r for r in results if r is not None]
        
        await ingestor.close()
        
        n = len(downloaded)
        logger.info(f"📦  Downloaded {n} source file{'s' if n != 1 else ''} — ready for analysis")
            
        return {"repo_metadata": repo_data, "downloaded_files": downloaded}

    async def node_cartograph(self, state: PipelineState):
        n_files = len(state["downloaded_files"])
        logger.info(f"🗺️   Mapping {n_files} files — building dependency graph...")
        # Run CPU-bound task in a thread to prevent blocking the event loop
        graph = await asyncio.to_thread(self.cartographer.analyze_repo, state["downloaded_files"])
        
        # Feature 7: Author Overlay
        owner = state["repo_metadata"]["owner"]
        repo = state["repo_metadata"]["repo"]
        files = [f["path"] for f in state["downloaded_files"]]
        
        blame_analyzer = GitBlameAnalyzer(state.get("session_token"))
        try:
            # Git Blame is an optional overlay. Never let it freeze the pipeline for more than 5 seconds.
            authors_map = await asyncio.wait_for(
                blame_analyzer.analyze_authors(owner, repo, files),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.warning("Git Blame took too long (>5s). Bypassing to prevent pipeline freeze.")
            authors_map = {}
        finally:
            await blame_analyzer.close()
            
        graph["authors"] = authors_map
        
        n_nodes = len(graph.get("nodes", []))
        n_edges = len(graph.get("calls", []))
        logger.info(f"✅  Graph built — {n_nodes} components, {n_edges} connections found")
        
        patterns, actions = await asyncio.to_thread(self.cartographer.pattern_scan, graph, state["downloaded_files"])
        logger.info(f"🛡️  Found {len(patterns)} patterns and {len(actions)} actionable insights")

        return {
            "graph": graph,
            "pattern_findings": patterns,
            "security_findings": graph.get("security_findings", []),
            "actions": actions
        }

    async def node_synthesize(self, state: PipelineState):
        retry_count = state.get("synthesis_retries", 0)
        if retry_count == 0:
            logger.info("🧠  AI is studying the codebase architecture...")
        else:
            logger.info(f"🔁  Refining analysis — correcting {retry_count} unverified claim(s)...")

        # On the first pass verifier_feedback is an empty string, so the Synthesizer
        # behaves identically to before. On subsequent retries the Verifier's rejection
        # report is injected as a corrective second human turn in the prompt, forcing
        # the model to address every failed claim rather than blindly re-running.
        feedback = state.get("verifier_feedback", "")
        result = await asyncio.to_thread(
            self.synthesizer.synthesize,
            state["graph"],
            state["downloaded_files"],
            feedback,
            state.get("mode", "technical"),
            state.get("session_token")
        )

        return {
            "claims": result["claims"],
            "narrative": result["narrative"],
            "synthesis_retries": retry_count + 1,
        }

    async def node_verify(self, state: PipelineState):
        n_claims = len(state.get("claims", []))
        logger.info(f"🔬  Verifying {n_claims} architectural claim{'s' if n_claims != 1 else ''} against source code...")
        verified_claims = await self.verifier.verify_claims_async(state["claims"], state["graph"], state["downloaded_files"], state.get("session_token"))
        
        feedback = ""
        unverified = [c for c in verified_claims if c["status"] == "Unverified"]
        for c in unverified:
            feedback += f"Claim '{c['claim']}' was Unverified. Reason: {c['reasoning']}\n"
        
        if unverified:
            logger.info(f"⚠️   {len(unverified)} claim(s) need correction — routing back to AI...")
        else:
            logger.info(f"✅  All claims verified against source code")
                
        return {"claims": verified_claims, "verifier_feedback": feedback}

    def route_after_verify(self, state: PipelineState):
        if state.get("verifier_feedback") and state.get("synthesis_retries", 0) < 2:
            logger.info("Verifier found issues, routing back to Synthesizer for retry.")
            return "retry"
        logger.info("Proceeding to Diagram Agent.")
        return "continue"

    async def node_diagram(self, state: PipelineState):
        logger.info("🎨  Drawing the architecture diagram...")
        mermaid = await asyncio.to_thread(
            self.diagram_agent.generate_diagram,
            state["graph"],
            state["narrative"],
            state.get("session_token")
        )
        return {"mermaid_diagram": mermaid}

    def node_write_readme(self, state: PipelineState):
        logger.info("📝  Writing architecture documentation...")
        readme = f"# Groundwork Architecture Analysis\n\n"
        readme += f"## Architecture Overview\n\n{state['narrative']}\n\n"
        readme += f"## Component Diagram\n\n```mermaid\n{state['mermaid_diagram']}\n```\n\n"
        logger.info("🎉  Analysis complete — results ready!")
        return {"readme_content": readme}
        
    async def run(self, repo_url: str, session_token: str = None, mode: str = "technical") -> Dict[str, Any]:
        initial_state = {
            "repo_url": repo_url,
            "session_token": session_token,
            "mode": mode,
            "repo_metadata": {},
            "downloaded_files": [],
            "graph": {},
            "claims": [],
            "narrative": "",
            "mermaid_diagram": "",
            "readme_content": "",
            "synthesis_retries": 0,
            "verifier_feedback": ""
        }
        
        final_state = await self.graph.ainvoke(initial_state)
        return final_state
