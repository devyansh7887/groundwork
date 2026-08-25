"use client";

import React from "react";

interface GraphData {
  files: string[];
  nodes: Array<any>;
  imports: Array<any>;
  calls: Array<any>;
  total_public_functions?: number;
  total_sloc?: number;
}

interface Props {
  graph: GraphData;
  fileSizes: Record<string, number>;
  fileLocs?: Record<string, number>;
  colorBy?: "folder" | "type" | "author";
  onColorByChange?: (val: "folder" | "type" | "author") => void;
  onFileSelect?: (f: string) => void;
}

export function ExplorerPanel({ graph, fileSizes, fileLocs = {}, colorBy = "folder", onColorByChange, onFileSelect }: Props) {
  const totalFiles = graph.files?.length || 0;
  // Use the accurate public function count from cartographer (named top-level functions only)
  const totalFunctions = graph.total_public_functions ?? graph.nodes?.length ?? 0;
  // Use import-based links (architectural module dependencies)
  const totalLinks = graph.imports?.length || 0;
  // Use SLOC (non-blank, non-comment) if available, else fall back to raw LOC
  const totalLoc = graph.total_sloc ?? (
    Object.values(fileLocs).reduce((a, b) => a + b, 0) ||
    Object.values(fileSizes || {}).reduce((a, b) => a + Math.round(b / 40), 0)
  );

  // Group files into a simple tree structure based on colorBy
  const tree: Record<string, string[]> = {};
  for (const f of graph.files || []) {
    let key = "root";
    if (colorBy === "folder") {
      const parts = f.split("/");
      key = parts.length > 1 ? parts[0] : "root";
    } else if (colorBy === "type") {
      const ext = f.split('.').pop()?.toLowerCase();
      key = ext ? `.${ext} files` : "unknown";
    } else if (colorBy === "author") {
      key = (graph as any).authors?.[f]?.primary_author || "Unknown Author";
    }
    
    if (!tree[key]) tree[key] = [];
    tree[key].push(f);
  }

  const unusedCount = 0; // Stub, would be calculated from graph logic

  return (
    <div className="w-full h-full flex flex-col bg-[#0d1117] border-r border-[#30363d] overflow-hidden text-[#c9d1d9] font-ibm">
      
      {/* Top Toggle area (matches Codeflow screenshot) */}
      <div className="p-4 border-b border-[#30363d]">
        <div className="text-[10px] text-[#8b949e] font-bold uppercase tracking-widest mb-3">Color By</div>
        <div className="flex flex-col gap-2">
          <button 
            onClick={() => onColorByChange?.("folder")}
            className={`flex items-center gap-2 px-3 py-2 border rounded-md text-sm font-semibold transition-colors ${
              colorBy === "folder" ? "bg-[#21262d] border-[#30363d] text-[#3fb950]" : "border-transparent text-[#8b949e] hover:bg-[#161b22]"
            }`}
          >
            <span>[/]</span> Folder
          </button>
          <button 
            onClick={() => onColorByChange?.("type")}
            className={`flex items-center gap-2 px-3 py-2 border rounded-md text-sm font-semibold transition-colors ${
              colorBy === "type" ? "bg-[#21262d] border-[#30363d] text-[#3fb950]" : "border-transparent text-[#8b949e] hover:bg-[#161b22]"
            }`}
          >
            <span>[L]</span> Type (Layer)
          </button>
          <button 
            onClick={() => onColorByChange?.("author")}
            className={`flex items-center gap-2 px-3 py-2 border rounded-md text-sm font-semibold transition-colors ${
              colorBy === "author" ? "bg-[#21262d] border-[#30363d] text-[#3fb950]" : "border-transparent text-[#8b949e] hover:bg-[#161b22]"
            }`}
          >
            <span>[A]</span> Author (Churn)
          </button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="p-4 border-b border-[#30363d]">
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="border border-[#30363d] bg-[#161b22] rounded-md p-3 text-center flex flex-col justify-center">
            <div className="text-[#58a6ff] text-xl font-bold font-jetbrains">{totalFiles}</div>
            <div className="text-[10px] text-[#8b949e] font-bold uppercase tracking-widest mt-1">Analyzed Files</div>
          </div>
          <div className="border border-[#30363d] bg-[#161b22] rounded-md p-3 text-center flex flex-col justify-center">
            <div className="text-[#58a6ff] text-xl font-bold font-jetbrains">{totalFunctions.toLocaleString()}</div>
            <div className="text-[10px] text-[#8b949e] font-bold uppercase tracking-widest mt-1">Exported Fns</div>
          </div>
          <div className="border border-[#30363d] bg-[#161b22] rounded-md p-3 text-center flex flex-col justify-center">
            <div className="text-[#3fb950] text-xl font-bold font-jetbrains">{totalLinks.toLocaleString()}</div>
            <div className="text-[10px] text-[#8b949e] font-bold uppercase tracking-widest mt-1">Import Links</div>
          </div>
          <div className="border border-[#30363d] bg-[#161b22] rounded-md p-3 text-center flex flex-col justify-center">
            <div className="text-[#8b949e] text-xl font-bold font-jetbrains">{graph.calls?.length?.toLocaleString() ?? 0}</div>
            <div className="text-[10px] text-[#8b949e] font-bold uppercase tracking-widest mt-1">Call Edges</div>
          </div>
        </div>

        <div className="border border-[#30363d] bg-[#161b22] rounded-md p-4 text-center">
          <div className="text-[#3fb950] text-2xl font-bold font-jetbrains">{totalLoc.toLocaleString()}</div>
          <div className="text-[10px] text-[#8b949e] font-bold uppercase tracking-widest mt-1">Lines of Code</div>
        </div>
      </div>

      {/* Explorer Tree */}
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        <div className="text-[10px] text-[#8b949e] font-bold uppercase tracking-widest mb-3">Explorer</div>
        <div className="space-y-1">
          {Object.entries(tree).sort((a,b) => b[1].length - a[1].length).map(([folder, files]) => (
            <div key={folder} className="group">
              <div className="flex items-center justify-between py-1.5 px-2 hover:bg-[#161b22] rounded cursor-pointer transition-colors">
                <div className="flex items-center gap-2">
                  <span className="text-[#8b949e]">[/]</span>
                  <span className="text-sm font-jetbrains text-[#c9d1d9]">{folder}</span>
                </div>
                <div className="text-xs text-[#484f58] font-jetbrains bg-[#21262d] px-1.5 rounded">{files.length}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
