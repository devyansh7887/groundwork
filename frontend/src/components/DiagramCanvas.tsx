"use client";

import dynamic from "next/dynamic";
import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import mermaid from "mermaid";
import { polygonHull } from "d3-polygon";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });
const ForceGraph3D = dynamic(() => import("react-force-graph-3d"), { ssr: false });
import SpriteText from 'three-spritetext';
import { TreemapView, TreeView, ClusterView, MatrixView, BundleView, BlockDiagramView } from "./D3Views";

// ─── Types ───────────────────────────────────────────────────────────────────
interface GraphData {
  files: string[];
  nodes: Array<{ id: string; name: string; type: string; line: number }>;
  imports: Array<{ source: string; target_module: string }>;
  calls: Array<{ caller_file: string; callee: string }>;
  entry_points: Array<{ id: string; reason: string }>;
  authors?: Record<string, { primary_author: string; authors: Record<string, number> }>;
}

interface Props {
  mermaidChart: string;
  graph: GraphData;
  fileSizes: Record<string, number>;
}

const TABS = ["Graph", "3D Graph", "Treemap", "Matrix", "Tree", "Flow", "Cluster", "Bundle", "Block Diagram"] as const;
type Tab = typeof TABS[number];

// ─── Color helpers ───────────────────────────────────────────────────────────
const FOLDER_COLORS = [
  "#58a6ff", "#3fb950", "#d29922", "#bc8cff", "#ff7b72",
  "#79c0ff", "#56d364", "#e3b341", "#d2a8ff", "#ffa198",
];

function folderColor(path: string, folders: string[]) {
  const folder = path.split("/")[0] ?? "root";
  const idx = folders.indexOf(folder);
  return FOLDER_COLORS[idx % FOLDER_COLORS.length];
}

function getTypeColor(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'ts': case 'tsx': case 'js': case 'jsx': return "#3fb950"; // Green
    case 'py': return "#58a6ff"; // Blue
    case 'java': case 'kt': case 'scala': return "#d2a8ff"; // Purple
    case 'c': case 'cpp': case 'h': case 'hpp': return "#ff7b72"; // Red
    case 'go': case 'rs': return "#1f6feb"; // Bright Blue
    case 'html': case 'css': case 'xml': case 'json': case 'yaml': case 'yml': case 'md': return "#e3b341"; // Yellow
    case 'sh': case 'bash': return "#238636"; // Dark Green
    default: return "#8b949e"; // Gray
  }
}

// ─── Build force graph data ───────────────────────────────────────────────────
function buildForceData(graph: GraphData, fileSizes: Record<string, number>, colorBy: "folder" | "type" | "author") {
  const fileSet = new Set(graph.files);
  const folders = [...new Set(graph.files.map(f => f.split("/")[0] ?? "root"))];

  const nodes = graph.files.map(f => ({
    id: f,
    name: f.split("/").pop() ?? f,
    val: Math.max(2, Math.min(20, (fileSizes[f] ?? 1000) / 500)),
    color: colorBy === "author" 
             ? (graph.authors?.[f]?.primary_author 
                 ? folderColor(graph.authors[f].primary_author, [...new Set(Object.values(graph.authors).map((a: any) => a.primary_author))])
                 : "#484f58") // Gray if no author data
             : colorBy === "type" 
             ? getTypeColor(f)
             : folderColor(f, folders),
    folder: f.split("/")[0] ?? "root",
    author: graph.authors?.[f]?.primary_author ?? "Unknown",
    commits: Object.values(graph.authors?.[f]?.authors || {}).reduce((a: any, b: any) => a + (b as number), 0),
    functions: graph.nodes ? graph.nodes.filter((n: any) => n.id && n.id.startsWith(f + ":")).length : 0,
    isEntry: graph.entry_points ? graph.entry_points.some((e: any) => e.id.startsWith(f)) : false,
  }));

  // Build file-level links from imports
  const linkSet = new Set<string>();
  const links: { source: string; target: string }[] = [];
  for (const imp of graph.imports) {
    const src = imp.source;
    const tgtMod = imp.target_module?.replace(/\./g, "/");
    const match = graph.files.find(f => {
      const noExt = f.replace(/\.[^/.]+$/, "");
      return noExt.endsWith(tgtMod);
    });
    if (match && match !== src && fileSet.has(src)) {
      const key = `${src}→${match}`;
      if (!linkSet.has(key)) {
        linkSet.add(key);
        links.push({ source: src, target: match });
      }
    }
  }
  return { nodes, links, folders };
}

// ─── Mermaid view ─────────────────────────────────────────────────────────────
function MermaidView({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!ref.current || !chart) return;
    const id = "mermaid-canvas-" + Math.random().toString(36).slice(2);
    mermaid.render(id, chart).then(({ svg }) => {
      if (ref.current) {
        ref.current.innerHTML = svg;
        const el = ref.current.querySelector("svg");
        if (el) { 
          el.removeAttribute("width"); 
          el.removeAttribute("height"); 
          el.style.maxWidth = "none"; 
        }
      }
    }).catch(e => setErr(e.message));
  }, [chart]);
  if (err) return <div className="text-red-400 p-4 text-sm font-jetbrains">{err}</div>;
  return <div className="w-full h-full overflow-auto cursor-grab active:cursor-grabbing border border-[#30363d] rounded bg-[#0d1117] p-8"><div ref={ref} className="min-w-fit min-h-fit origin-top-left hover:scale-[1.02] transition-transform duration-300" /></div>;
}

// ─── Main DiagramCanvas ───────────────────────────────────────────────────────
interface DiagramCanvasProps {
  mermaidChart?: string;
  graph: any;
  fileSizes: Record<string, number>;
  colorBy?: "folder" | "type" | "author";
  onColorByChange?: (color: "folder" | "type" | "author") => void;
}

export function DiagramCanvas({ mermaidChart = "", graph, fileSizes, colorBy = "folder", onColorByChange }: DiagramCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [activeTab, setActiveTab] = useState<Tab>("Flow");
  const [isMaximized, setIsMaximized] = useState(false);
  const fgRef = useRef<any>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 504 });

  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setDimensions({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [isMaximized, activeTab]);

  const forceData = useMemo(() => buildForceData(graph, fileSizes, colorBy), [graph, fileSizes, colorBy]);

  // Configure Force Graph physics for large repos
  useEffect(() => {
    if (fgRef.current && activeTab === "Graph") {
      fgRef.current.d3Force('charge').strength(-200); // Stronger repulsion
      fgRef.current.d3Force('link').distance(60);     // Longer links
      fgRef.current.d3Force('center').strength(0.05); // Looser centering
    }
  }, [activeTab, forceData]);

  // Escape key closes expanded modal
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsMaximized(false); };
    if (isMaximized) window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isMaximized]);

  const nodeCount = graph.files.length;

  const colorMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const n of forceData.nodes) {
      if (n.id) map[n.id] = (n as any).color;
    }
    return map;
  }, [forceData.nodes]);

  const content = (
    <div className={`w-full flex flex-col bg-[#0d1117] transition-all duration-300 ${isMaximized ? "h-full border-none" : "rounded-xl border border-[#30363d] overflow-hidden"}`} style={{ height: isMaximized ? undefined : 560 }}>
      {/* Tab bar */}
      <div className="flex items-center gap-1 px-4 py-2 bg-[#161b22] border-b border-[#30363d] overflow-x-auto">
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1 rounded-md text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === tab
                ? "bg-[#58a6ff] text-white"
                : "text-[#8b949e] hover:text-[#c9d1d9] hover:bg-[#21262d]"
            }`}
          >
            {tab === "Flow" ? " Flow" :
             tab === "Graph" ? " Graph" : 
             tab === "3D Graph" ? " 3D Graph" : 
             tab === "Treemap" ? " Treemap" : 
             tab === "Matrix" ? " Matrix" : 
             tab === "Tree" ? " Tree" : 
             tab === "Cluster" ? " Cluster" : 
             tab === "Bundle" ? " Bundle" : 
             tab === "Block Diagram" ? " Block Diagram" : tab}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-3">
          <span className="text-[10px] text-[#484f58] font-jetbrains">{nodeCount} files · {forceData.links.length} edges</span>
          <button 
            onClick={() => setIsMaximized(!isMaximized)}
            className="text-[#8b949e] hover:text-[#c9d1d9] transition-colors p-1 rounded hover:bg-[#30363d]"
            title={isMaximized ? "Restore" : "Maximize"}
          >
            {isMaximized ? <span>[_]</span> : <span>[^]</span>}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="w-full flex-1 overflow-hidden relative" ref={containerRef}>
        {activeTab === "Flow" && <MermaidView chart={mermaidChart} />}

        {activeTab === "Graph" && forceData.nodes.length > 0 && (
          <ForceGraph2D
            ref={fgRef}
            key={colorBy}
            graphData={{ nodes: forceData.nodes, links: forceData.links }}
            nodeLabel={(node: any) => `
              <div style="background: rgba(13,17,23,0.95); border: 1px solid #30363d; border-radius: 8px; padding: 12px; font-family: monospace; text-align: left; min-width: 180px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);">
                <div style="color: ${node.color}; font-weight: bold; margin-bottom: 2px; font-size: 14px;">${node.name}</div>
                <div style="color: #c9d1d9; margin-bottom: 8px; font-size: 12px;">${node.folder}</div>
                <div style="color: #8b949e; font-size: 11px;">
                  ${node.functions} functions &bull; ${node.folder} layer &bull; ${node.commits} commits
                </div>
              </div>
            `}
            nodeColor={n => (n as any).color}
            nodeVal={n => (n as any).val}
            linkColor={() => "#30363d"}
            backgroundColor="#0d1117"
            onRenderFramePre={(ctx: CanvasRenderingContext2D, globalScale: number) => {
              // Always group nodes by folder to draw hulls, regardless of colorBy
              const groups: Record<string, [number, number][]> = {};
              const colors: Record<string, string> = {};
              for (const node of forceData.nodes as any[]) {
                if (node.x != null && node.y != null) {
                  if (!groups[node.folder]) groups[node.folder] = [];
                  groups[node.folder].push([node.x, node.y]);
                  // Use dedicated folder color for the hull so it remains consistent
                  colors[node.folder] = folderColor(node.folder, forceData.folders);
                }
              }

              // Draw hulls
              for (const [folder, coords] of Object.entries(groups)) {
                if (coords.length < 3) continue; // polygonHull needs at least 3 points
                const hull = polygonHull(coords);
                if (hull) {
                  ctx.beginPath();
                  ctx.moveTo(hull[0][0], hull[0][1]);
                  for (let i = 1; i < hull.length; i++) {
                    ctx.lineTo(hull[i][0], hull[i][1]);
                  }
                  ctx.closePath();
                  ctx.fillStyle = colors[folder] + "22"; // 13% opacity
                  ctx.fill();
                  ctx.strokeStyle = colors[folder] + "55";
                  ctx.lineWidth = 15 / globalScale;
                  ctx.lineJoin = "round";
                  ctx.stroke();
                }
              }
            }}
            nodeCanvasObjectMode={() => "after"}
            nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
              if (globalScale < 2) return;
              ctx.font = `${10 / globalScale}px monospace`;
              ctx.fillStyle = "#c9d1d9";
              const label = colorBy === "author" ? `${node.name} (${node.author})` : node.name;
              ctx.fillText(label, node.x + 6, node.y + 3);
            }}
            width={dimensions.width}
            height={dimensions.height}
          />
        )}


        {activeTab === "3D Graph" && forceData.nodes.length > 0 && (
          <ForceGraph3D
            key={colorBy}
            graphData={{ nodes: forceData.nodes, links: forceData.links }}
            nodeLabel={(node: any) => `
              <div style="background: rgba(13,17,23,0.95); border: 1px solid #30363d; border-radius: 8px; padding: 12px; font-family: monospace; text-align: left; min-width: 180px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);">
                <div style="color: ${node.color}; font-weight: bold; margin-bottom: 2px; font-size: 14px;">${node.name}</div>
                <div style="color: #c9d1d9; margin-bottom: 8px; font-size: 12px;">${node.folder}</div>
                <div style="color: #8b949e; font-size: 11px;">
                  ${node.functions} functions &bull; ${node.folder} layer &bull; ${node.commits} commits
                </div>
              </div>
            `}
            nodeColor={(n: any) => n.color}
            nodeVal={(n: any) => n.val}
            nodeThreeObjectExtend={true}
            nodeThreeObject={(node: any) => {
              const sprite = new SpriteText(node.name);
              sprite.color = node.color;
              sprite.textHeight = 4;
              sprite.backgroundColor = "transparent";
              sprite.padding = 0;
              // offset text so it hovers above the node
              sprite.position.y = Math.max(3, node.val) + 2;
              return sprite;
            }}
            linkColor={() => "#30363d"}
            backgroundColor="#0d1117"
            width={dimensions.width}
            height={dimensions.height}
          />
        )}

        {activeTab === "Treemap" && (
          <div className="w-full h-full overflow-hidden">
            <TreemapView graph={graph} fileSizes={fileSizes} colorMap={colorMap} width={dimensions.width} height={dimensions.height} />
          </div>
        )}

        {activeTab === "Tree" && (
          <div className="w-full h-full overflow-auto">
            <TreeView graph={graph} fileSizes={fileSizes} colorMap={colorMap} width={dimensions.width} height={dimensions.height} />
          </div>
        )}

        {activeTab === "Cluster" && (
          <div className="w-full h-full overflow-auto">
            <ClusterView graph={graph} fileSizes={fileSizes} colorMap={colorMap} width={dimensions.width} height={dimensions.height} />
          </div>
        )}

        {activeTab === "Matrix" && (
          <div className="w-full h-full overflow-auto">
            <MatrixView graph={graph} fileSizes={fileSizes} colorMap={colorMap} width={dimensions.width} height={dimensions.height} />
          </div>
        )}

        {activeTab === "Bundle" && (
          <div className="w-full h-full overflow-hidden flex items-center justify-center">
            <BundleView graph={graph} fileSizes={fileSizes} colorMap={colorMap} width={dimensions.width} height={dimensions.height} />
          </div>
        )}

        {activeTab === "Block Diagram" && (
          <div className="w-full h-full overflow-auto p-4 bg-[#0d1117]">
            <BlockDiagramView graph={graph} fileSizes={fileSizes} colorMap={colorMap} width={dimensions.width} height={dimensions.height} />
          </div>
        )}

        {["Graph", "3D Graph"].includes(activeTab) && forceData.nodes.length === 0 && (
          <div className="flex items-center justify-center h-full text-[#484f58] text-sm font-jetbrains">
            No file graph data available for this repository.
          </div>
        )}
      </div>
    </div>
  );

  if (isMaximized) {
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4 md:p-8">
        <div className="w-full h-full max-w-[85vw] max-h-[85vh] flex animate-in fade-in zoom-in-95 duration-200 bg-[#0d1117] rounded-xl border border-[#30363d] overflow-hidden">
          {content}
        </div>
      </div>
    );
  }

  return content;
}
