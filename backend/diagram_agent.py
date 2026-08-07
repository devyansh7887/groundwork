import json
import logging
import time
from typing import Dict, Any, List, Optional
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
"""

HUMAN_PROMPT = """Analyze this codebase and produce a clean component-level architecture diagram.

Architecture Narrative (ground truth):
{narrative}

File List (representative, not exhaustive):
{files}

Key Topology (calls & imports observed by static analysis):
{topology}

Remember: merge files that share a single responsibility into ONE component.
Aim for 8-15 total components. Every edge needs a label.
"""

class DiagramAgent:
    def __init__(self):
        pass

    def _safe_id(self, s: str) -> str:
        """Convert any string to a safe Mermaid node id."""
        return s.replace(" ", "_").replace("-", "_").replace("/", "_").replace(".", "_").replace("(", "").replace(")", "")

    def _build_topology_summary(self, graph: Dict[str, Any], max_entries: int = 60) -> str:
        """Build a concise topology string for the LLM prompt."""
        lines = []
        for call in graph.get("calls", [])[:max_entries // 2]:
            caller = call.get("caller_file", "").split("/")[-1]
            callee = call.get("callee", "")
            if caller and callee:
                lines.append(f"{caller} → calls → {callee}")
        for imp in graph.get("imports", [])[:max_entries // 2]:
            source = imp.get("source", "").split("/")[-1]
            target = imp.get("target_module", "")
            if source and target:
                lines.append(f"{source} → imports → {target}")
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

        # Calculate centrality (how often a file is imported or called) to pick the most architecturally significant files
        from collections import Counter
        centrality = Counter()
        for imp in graph.get("imports", []):
            tgt = imp.get("target_module", "").split(".")[-1]
            for f in valid_files:
                if f.endswith(tgt + ".py") or f.endswith(tgt + ".ts") or f.endswith(tgt + ".tsx"):
                    centrality[f] += 1
                    break
        
        # Sort by centrality (descending), fallback to alphabetical
        important_files = sorted(valid_files, key=lambda x: (centrality[x], x), reverse=True)[:20]

        topology_summary = self._build_topology_summary(graph)

        logger.info(f"Diagram Agent: generating component diagram from {len(all_files)} files → targeting 8-15 components")

        # Exponential backoff retry loop
        max_retries = 5
        backoff = 1.0
        diagram_output: Optional[ComponentDiagramOutput] = None

        for attempt in range(1, max_retries + 1):
            try:
                llm = llm_key_pool.get_llm(session_token, temperature=0.1)
                structured_llm = llm.with_structured_output(ComponentDiagramOutput)
                chain = prompt | structured_llm
                diagram_output = chain.invoke({
                    "narrative": narrative[:3000],  # trim to avoid token limits
                    "files": json.dumps(important_files),
                    "topology": topology_summary,
                })
                logger.info(f"LLM returned {len(diagram_output.components)} components and {len(diagram_output.edges)} edges")
                break
            except Exception as e:
                logger.warning(f"LLM attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error("All retries exhausted. Returning fallback diagram.")
                    return 'flowchart TB\n    fallback["⚠️ Diagram generation failed — rate limit or LLM error"]\n    style fallback fill:#1e293b,stroke:#475569,color:#cbd5e1'
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

        return self._render_mermaid(diagram_output)

    def _render_mermaid(self, output: ComponentDiagramOutput) -> str:
        """
        Renders the ComponentDiagramOutput as Mermaid flowchart syntax
        following the reference spec exactly.
        """
        lines = ["flowchart TB"]
        lines.append("")

        # Build component lookup for validation
        valid_ids = {c.component_id for c in output.components}
        comp_map = {c.component_id: c for c in output.components}

        # Build layer → component mapping
        layer_component_ids: Dict[str, List[str]] = {}
        for layer in output.layers:
            layer_component_ids[layer.layer_id] = layer.components

        # Track which components are placed in a layer
        placed = set()

        # ── Emit each architectural layer as a subgraph ──────────────────────
        for layer in output.layers:
            lid = self._safe_id(layer.layer_id)
            # Escape quotes in layer label
            layer_label = layer.layer_label.replace('"', "'")
            lines.append(f'    subgraph {lid}["{layer_label}"]')

            for cid in layer.components:
                if cid not in comp_map:
                    continue
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
        orphans = [c for c in output.components if c.component_id not in placed]
        if orphans:
            lines.append("    %% Ungrouped components")
            for comp in orphans:
                node_id = self._safe_id(comp.component_id)
                node_label = comp.label.replace('"', "'")
                lines.append(f'    {node_id}["{node_label}"]')
            lines.append("")

        # ── Emit edges ────────────────────────────────────────────────────────
        lines.append("    %% Connections")
        seen_edges = set()
        for edge in output.edges:
            src = edge.from_component
            dst = edge.to_component
            # Skip edges to unknown components
            if src not in valid_ids or dst not in valid_ids:
                continue
            src_id = self._safe_id(src)
            dst_id = self._safe_id(dst)
            edge_label = edge.label.replace('"', "'")
            key = (src_id, dst_id, edge_label)
            if key in seen_edges:
                continue
            seen_edges.add(key)

            if edge.is_async:
                lines.append(f'    {src_id} -.->|"{edge_label}"| {dst_id}')
            else:
                lines.append(f'    {src_id} -->|"{edge_label}"| {dst_id}')

        lines.append("")

        # ── Node styling via classDef (Mermaid v11 compliant) ─────────────────
        lines.append("    classDef controller fill:#1e3a5f,stroke:#3b82f6,stroke-width:2px,color:#bfdbfe")
        lines.append("    classDef service fill:#14352a,stroke:#22c55e,stroke-width:2px,color:#bbf7d0")
        lines.append("    classDef store fill:#3b1f00,stroke:#f59e0b,stroke-width:2px,color:#fde68a")
        lines.append("    classDef queue fill:#2d1b69,stroke:#8b5cf6,stroke-width:2px,color:#ddd6fe")
        lines.append("    classDef client fill:#1e293b,stroke:#94a3b8,stroke-width:2px,color:#e2e8f0")
        lines.append("")

        # Apply classes
        for comp in output.components:
            node_id = self._safe_id(comp.component_id)
            node_type = comp.node_type if comp.node_type in ("controller", "service", "store", "queue", "client") else "service"
            lines.append(f"    class {node_id} {node_type}")

        return "\n".join(lines)
