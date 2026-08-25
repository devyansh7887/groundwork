import json
import logging
import time
from typing import Dict, Any, List, Optional
from collections import Counter
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from llm_key_pool import llm_key_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models for the COMPONENT-level diagram output
# ─────────────────────────────────────────────────────────────────────────────

class ComponentEdge(BaseModel):
    from_component: str = Field(description="The component_id of the source component")
    to_component: str = Field(description="The component_id of the target component")
    label: str = Field(description="Short label describing what crosses this boundary, e.g. 'save(url, code)' or 'HTTP GET /api'. Never just 'uses'.")
    is_async: bool = Field(default=False, description="True for async/event/queue relationships (renders as dashed arrow)")

class ArchitecturalLayer(BaseModel):
    layer_id: str = Field(description="A short snake_case id like 'api_layer', 'service_layer', 'data_layer'")
    layer_label: str = Field(description="Human-readable subgraph title, e.g. 'API Layer -- HTTP' or 'Service Layer -- Business Logic'")
    components: List[str] = Field(description="List of component_ids that belong in this layer")

class Component(BaseModel):
    component_id: str = Field(description="Short snake_case identifier, e.g. 'auth_service', 'url_repository'")
    label: str = Field(description="Human-readable name shown in the diagram node, e.g. 'AuthService'")
    node_type: str = Field(description="One of: 'service' (rectangle), 'store' (cylinder/database), 'queue' (double-bracket), 'client' (rounded rectangle), 'controller' (rectangle)")
    files: List[str] = Field(description="The actual source file paths that implement this component (from the provided file list)")

class ComponentDiagramOutput(BaseModel):
    components: List[Component] = Field(
        description="All identified components. CRITICAL: one component = one RESPONSIBILITY, not one file. A 100-file repo should have 8-15 components MAX."
    )
    layers: List[ArchitecturalLayer] = Field(
        description="Architectural layers/subgraphs grouping related components. Typical layers: Client, API Layer, Middleware, Service Layer, Data Access Layer, Background Workers, External Systems."
    )
    edges: List[ComponentEdge] = Field(
        description="Directed edges between component_ids. Every edge MUST have a descriptive label. Use is_async=True for events, queues, and cache reads."
    )

# ─────────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert software architect who draws COMPONENT-LEVEL architecture diagrams.

## Your Prime Directive
Draw at the RESPONSIBILITY level, NOT the file level.
- A repo with 100 files should produce 8–15 components MAX.
- Ask: "What is the single job of this group of files?" — that is one component.
- Files that serve the same responsibility belong in the SAME component node.

## Component Types
- `controller`  → API endpoints, route handlers, view controllers
- `service`     → Business logic, use-cases, domain services
- `store`       → Databases, caches, persistent storage (render as cylinder)
- `queue`       → Async brokers, event buses, Kafka topics (render as double-bracket)
- `client`      → External callers, browsers, third-party services

## Layer Naming (use these or adapt if missing)
- Client Layer
- API Layer -- HTTP
- Middleware
- Service Layer -- Business Logic
- Data Access Layer
- Background Workers
- External Systems

## Edge Labels
Every edge MUST be labeled with WHAT crosses the boundary.
Good: "save(url, code)", "HTTP GET /:code", "publish ClickEvent", "cache-aside read"
Bad: "uses", "calls", "depends on"

## Rules
1. NEVER create one component per file. Merge related files.
2. NEVER create more than 15 components total.
3. NEVER leave an edge unlabeled.
4. Async edges (events, queues, cache reads) → is_async = True
5. Do NOT invent components for technologies not present in the codebase.
6. Every component's `files` list must only contain paths from the provided file list.
"""

HUMAN_PROMPT = """Analyze this codebase and produce a clean component-level architecture diagram.

Architecture Narrative (ground truth — read carefully):
{narrative}

Key Files (ranked by architectural importance):
{files}

Critical Architecture Topology (most-called functions and their call patterns):
{topology}

REMINDER: Group files that share a responsibility into ONE component. Target 8-15 total components. Every edge needs a meaningful label (not just 'uses').
"""

class DiagramAgent:
    def __init__(self):
        pass

    def _safe_id(self, s: str) -> str:
        """Convert any string to a safe Mermaid node id."""
        import re
        safe = re.sub(r'[^a-zA-Z0-9_]', '_', s)
        # Ensure it doesn't start with a digit
        if safe and safe[0].isdigit():
            safe = 'n_' + safe
        return safe[:40]  # Cap length to prevent overly long IDs

    def _build_ranked_topology(self, graph: Dict[str, Any], max_entries: int = 40) -> str:
        """
        Build a topology string ranked by FREQUENCY — the most-called functions
        and most-used imports appear first, giving the LLM the architectural spine.
        """
        # Rank calls by frequency of callee
        call_freq = Counter(call.get("callee", "") for call in graph.get("calls", []))
        
        # Rank imports by how often a module is imported
        import_freq = Counter(imp.get("target_module", "") for imp in graph.get("imports", []))
        
        lines = []
        seen_calls = set()
        
        # Top calls by frequency
        for call in sorted(graph.get("calls", []), key=lambda c: call_freq.get(c.get("callee",""), 0), reverse=True):
            if len(lines) >= max_entries // 2:
                break
            caller = call.get("caller_file", "").split("/")[-1]
            callee = call.get("callee", "")
            key = (caller, callee)
            if caller and callee and key not in seen_calls:
                seen_calls.add(key)
                freq = call_freq[callee]
                lines.append(f"{caller} → calls → {callee} (×{freq})")
        
        # Top imports by frequency
        seen_imports = set()
        for imp in sorted(graph.get("imports", []), key=lambda i: import_freq.get(i.get("target_module",""), 0), reverse=True):
            if len(lines) >= max_entries:
                break
            source = imp.get("source", "").split("/")[-1]
            target = imp.get("target_module", "")
            key = (source, target)
            if source and target and key not in seen_imports:
                seen_imports.add(key)
                freq = import_freq[target]
                lines.append(f"{source} → imports → {target} (×{freq})")

        return "\n".join(lines) if lines else "No topology data available."

    def generate_diagram(self, graph: Dict[str, Any], narrative: str, session_token: str | None = None) -> str:
        """
        Generates a clean, component-level Mermaid flowchart.
        One node = one responsibility. Target 8-15 components max.
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", HUMAN_PROMPT),
        ])

        # Filter out tests and build artifacts
        all_files = graph.get("files", [])
        valid_files = [
            f for f in all_files
            if not any(x in f.lower() for x in ["test", "spec", "__pycache__", ".min.", "node_modules", "dist/", "build/"])
        ]

        # Rank files by architectural centrality
        # Fix: For TypeScript, also match by relative path components, not just dotted module names
        centrality = Counter()
        for imp in graph.get("imports", []):
            tgt = imp.get("target_module", "")
            # Handle both Python dot-notation AND TypeScript/JS relative imports
            tgt_parts = [tgt.split(".")[-1], tgt.split("/")[-1], tgt.replace("./", "").replace("../", "")]
            for f in valid_files:
                f_base = f.split("/")[-1].rsplit(".", 1)[0]
                if any(f_base == part for part in tgt_parts if part):
                    centrality[f] += 1
                    break
        
        # Also count call centrality
        for call in graph.get("calls", []):
            callee = call.get("callee", "")
            for node in graph.get("nodes", []):
                if node.get("name") == callee:
                    fpath = node.get("id", "").split(":")[0]
                    if fpath in centrality:
                        centrality[fpath] += 1

        # Sort by centrality (descending), top 15 for LLM context to prevent token limits
        important_files = sorted(valid_files, key=lambda x: centrality.get(x, 0), reverse=True)[:15]
        
        topology_summary = self._build_ranked_topology(graph)

        logger.info(f"Diagram Agent: generating component diagram from {len(all_files)} files → targeting 8-15 components")

        # Exponential backoff retry loop
        max_retries = 6
        backoff = 2.0
        diagram_output: Optional[ComponentDiagramOutput] = None

        for attempt in range(1, max_retries + 1):
            try:
                llm = llm_key_pool.get_llm(session_token, temperature=0.1)
                structured_llm = llm.with_structured_output(ComponentDiagramOutput)
                chain = prompt | structured_llm
                diagram_output = chain.invoke({
                    "narrative": narrative[:2000],  # Cap to 2000 chars to avoid rate limits
                    "files": json.dumps(important_files),
                    "topology": topology_summary,
                })
                logger.info(f"LLM returned {len(diagram_output.components)} components and {len(diagram_output.edges)} edges")
                break
            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "rate limit" in error_str or "quota" in error_str or "exhausted" in error_str:
                    llm_key_pool.mark_rate_limit_for_llm(llm)
                        
                logger.warning(f"Diagram Agent attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error("All retries exhausted for diagram agent. Returning generic failure block.")
                    # Must escape double quotes and wrap in them so Mermaid doesn't choke on error strings containing () or '
                    error_safe = str(e).replace('"', "'").replace('\n', ' ')
                    return f'graph TD\n    A["⚠️ Diagram generation failed: {error_safe}"]\n    B["Please try again or provide a custom API token"]'
                time.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

        return self._render_mermaid(diagram_output)

    def _render_mermaid(self, output: ComponentDiagramOutput) -> str:
        """
        Renders the ComponentDiagramOutput as clean Mermaid flowchart syntax.
        Enforces: max 15 components, deduped edges, safe IDs, no orphan nodes.
        """
        lines = ["flowchart TB"]
        lines.append("")

        # Enforce max 15 components to prevent visual chaos
        components = output.components[:15]
        
        # Build lookup tables
        valid_ids = {c.component_id for c in components}
        comp_map = {c.component_id: c for c in components}

        # Track which components are placed in a layer
        placed = set()

        # ── Emit each architectural layer as a subgraph ──────────────────────
        for layer in output.layers:
            # Only emit layers that have at least one valid component
            valid_layer_comps = [cid for cid in layer.components if cid in comp_map]
            if not valid_layer_comps:
                continue
                
            lid = self._safe_id(layer.layer_id)
            layer_label = layer.layer_label.replace('"', "'")
            lines.append(f'    subgraph {lid}["{layer_label}"]')
            lines.append('    direction TB')

            for cid in valid_layer_comps:
                comp = comp_map[cid]
                node_id = self._safe_id(cid)
                node_label = comp.label.replace('"', "'")

                if comp.node_type == "store":
                    lines.append(f'        {node_id}[("{node_label}")]')
                elif comp.node_type == "queue":
                    lines.append(f'        {node_id}[["{node_label}"]]')
                elif comp.node_type == "client":
                    lines.append(f'        {node_id}("{node_label}")')
                else:
                    # controller, service, default
                    lines.append(f'        {node_id}["{node_label}"]')

                placed.add(cid)

            lines.append("    end")
            lines.append("")

        # ── Emit any un-layered components at the top level ──────────────────
        orphans = [c for c in components if c.component_id not in placed]
        if orphans:
            lines.append("    %% Ungrouped components")
            for comp in orphans:
                node_id = self._safe_id(comp.component_id)
                node_label = comp.label.replace('"', "'")
                lines.append(f'    {node_id}["{node_label}"]')
            lines.append("")

        # ── Emit edges (deduplicated, only between valid components) ──────────
        lines.append("    %% Connections")
        seen_edges = set()
        edge_count = 0
        
        for edge in output.edges:
            src = edge.from_component
            dst = edge.to_component
            # Skip edges to unknown components or self-loops
            if src not in valid_ids or dst not in valid_ids or src == dst:
                continue
            src_id = self._safe_id(src)
            dst_id = self._safe_id(dst)
            edge_label = edge.label.replace('"', "'")[:50]  # Cap label length
            key = (src_id, dst_id)  # Allow same connection with different labels (dedupe by src+dst only)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edge_count += 1

            if edge.is_async:
                lines.append(f'    {src_id} -.->|"{edge_label}"| {dst_id}')
            else:
                lines.append(f'    {src_id} -->|"{edge_label}"| {dst_id}')
        
        logger.info(f"Diagram rendered: {len(placed) + len(orphans)} components, {edge_count} edges")
        lines.append("")

        # ── Node styling via classDef ─────────────────────────────────────────
        lines.append("    classDef controller fill:#1e3a5f,stroke:#3b82f6,stroke-width:2px,color:#bfdbfe")
        lines.append("    classDef service fill:#14352a,stroke:#22c55e,stroke-width:2px,color:#bbf7d0")
        lines.append("    classDef store fill:#3b1f00,stroke:#f59e0b,stroke-width:2px,color:#fde68a")
        lines.append("    classDef queue fill:#2d1b69,stroke:#8b5cf6,stroke-width:2px,color:#ddd6fe")
        lines.append("    classDef client fill:#1e293b,stroke:#94a3b8,stroke-width:2px,color:#e2e8f0")
        lines.append("")

        # Apply classes
        for comp in components:
            node_id = self._safe_id(comp.component_id)
            node_type = comp.node_type if comp.node_type in ("controller", "service", "store", "queue", "client") else "service"
            lines.append(f"    class {node_id} {node_type}")

        return "\n".join(lines)
