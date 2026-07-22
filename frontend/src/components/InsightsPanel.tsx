"use client";

import React, { useMemo, useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";

interface GraphData {
  files: string[];
  nodes: Array<{ id: string; name: string; type: string }>;
  imports: Array<{ source: string; target_module: string }>;
  calls: Array<{ caller_file: string; callee: string }>;
  entry_points: Array<{ id: string; reason: string }>;
  authors?: Record<string, { primary_author: string; authors: Record<string, number> }>;
  action_findings?: Array<{
    title: string;
    severity: string;
    description: string;
    action: string;
    impact: string;
    target_file: string;
  }>;
}

interface Claim {
  claim: string;
  cited_file: string;
  cited_symbol?: string;
  status?: string;
}

interface SecurityFinding {
  file: string;
  line: number;
  type: string;
  severity: string;
  snippet: string;
  impact?: string;
  remediation?: string;
}

interface PatternFinding {
  type: string;
  severity: string;
  file: string;
  detail: string;
}

interface Props {
  graph: GraphData;
  fileSizes: Record<string, number>;
  fileLocs?: Record<string, number>;
  claims: Claim[];
  readme: string;
  security: SecurityFinding[];
  patterns: PatternFinding[];
  onActionSelect?: (action: any) => void;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#ff7b72",
  high: "#f78166",
  medium: "#d29922",
  warning: "#d29922",
  info: "#58a6ff",
  low: "#3fb950",
};

const SEVERITY_BG: Record<string, string> = {
  critical: "#ff7b7218",
  high: "#ff7b7212",
  medium: "#d2992218",
  warning: "#d2992218",
  info: "#58a6ff18",
  low: "#3fb95018",
};

type InsightTab = "OVERVIEW" | "PATTERNS" | "SECURITY" | "ACTIONS" | "EXPERTS";

export function InsightsPanel({ graph, fileSizes, fileLocs = {}, claims, readme, security, patterns, onActionSelect }: Props) {
  const [activeTab, setActiveTab] = useState<InsightTab>("OVERVIEW");
  const [isExpanded, setIsExpanded] = useState(false);

  // Escape key closes expanded modal
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsExpanded(false); };
    if (isExpanded) window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isExpanded]);

  const actionsCount = (graph.action_findings?.length || 0) + claims.filter(c => c.status === "Unverified").length;
  const issuesCount = (graph.action_findings?.length || 0);

  const tabs: { id: InsightTab; label: string; count?: number }[] = [
    { id: "OVERVIEW", label: "📊 OVERVIEW" },
    { id: "PATTERNS", label: "🧩 PATTERNS", count: patterns.length },
    { id: "SECURITY", label: "🔒 SECURITY", count: security.filter(s => s.severity !== "info").length },
    { id: "ACTIONS", label: "⚡ ACTIONS", count: actionsCount },
    ...(graph.authors ? [{ id: "EXPERTS", label: "🧑‍💻 Experts" } as const] : []),
  ];

  // Health score
  const totalFiles = graph.files.length;
  const totalNodes = graph.nodes.length;
  const securityIssues = security.filter(s => ["critical", "high"].includes(s.severity)).length;
  const patternIssues = patterns.filter(p => p.severity === "warning").length;
  const score = Math.max(0, Math.min(100,
    100
    - (securityIssues * 10)
    - (patternIssues * 5)
    - (totalFiles > 200 ? 10 : 0)
  ));

  const scoreColor = score >= 80 ? "#3fb950" : score >= 50 ? "#d29922" : "#ff7b72";
  const scoreLabel = score >= 80 ? "Healthy" : score >= 50 ? "Fair" : "Needs Attention";

  // Stats
  const totalLoc = Object.values(fileLocs).reduce((a, b) => a + b, 0) || Object.values(fileSizes || {}).reduce((a, b) => a + Math.round(b / 40), 0);
  const linkCount = graph.imports.length;
  const entryCount = graph.entry_points.length;

  // Language breakdown
  const langMap: Record<string, number> = {};
  for (const f of graph.files) {
    const lang = f.endsWith(".py") ? "Python" : f.endsWith(".ts") || f.endsWith(".tsx") ? "TypeScript" : "JavaScript";
    langMap[lang] = (langMap[lang] ?? 0) + 1;
  }

  const content = (
    <div className={`w-full rounded-xl border border-[#30363d] bg-[#0d1117] overflow-hidden flex flex-col ${isExpanded ? 'h-full border-none' : ''}`} style={{ minHeight: isExpanded ? undefined : 400 }}>
      {/* Header with health score */}
      <div className="px-4 py-3 bg-[#161b22] border-b border-[#30363d] flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <div className="w-12 h-12 rounded-full border-2 flex items-center justify-center flex-shrink-0"
              style={{ borderColor: scoreColor }}>
              <span className="text-lg font-bold" style={{ color: scoreColor }}>{score}</span>
            </div>
            <div>
              <div className="text-xs font-bold" style={{ color: scoreColor }}>{scoreLabel}</div>
              <div className="text-[10px] text-[#484f58]">Health Score</div>
            </div>
          </div>

          <div className="flex flex-wrap gap-4 text-xs font-mono">
            {[
              { label: "Files", val: totalFiles },
              { label: "Symbols", val: totalNodes },
              { label: "Links", val: linkCount },
              { label: "Entries", val: entryCount },
            ].map(({ label, val }) => (
              <div key={label} className="flex flex-col items-center">
                <span className="text-[#c9d1d9] font-bold text-sm">{val}</span>
                <span className="text-[#484f58]">{label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-4 items-center justify-end">
          <div className="flex gap-2">
            {Object.entries(langMap).map(([lang, count]) => (
              <span key={lang} className="text-[10px] font-mono bg-[#21262d] border border-[#30363d] px-2 py-0.5 rounded text-[#8b949e]">
                {lang}: {count}
              </span>
            ))}
          </div>
          <button 
            onClick={() => setIsExpanded(!isExpanded)} 
            className="text-[#8b949e] hover:text-[#c9d1d9] flex items-center justify-center transition-colors bg-[#21262d] border border-[#30363d] rounded p-1"
            title={isExpanded ? "Minimize" : "Expand"}
          >
            {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#30363d] bg-[#161b22] overflow-x-auto whitespace-nowrap custom-scrollbar">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            className={`flex-shrink-0 px-4 py-2 text-xs font-semibold flex items-center gap-1.5 transition-colors ${
              activeTab === t.id
                ? "text-[#58a6ff] border-b-2 border-[#58a6ff]"
                : "text-[#8b949e] hover:text-[#c9d1d9]"
            }`}>
            {t.label}
            {t.count != null && t.count > 0 && (
              <span className="rounded-full bg-[#21262d] text-[#8b949e] px-1.5 py-px text-[10px]">{t.count}</span>
            )}
          </button>
        ))}
      </div>

      {/* Panel body */}
      <div className="flex-1 overflow-y-auto p-4 bg-[#0d1117]">
        {activeTab === "OVERVIEW" && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              {[
                { title: "Architecture Pattern", val: totalFiles > 50 ? "Multi-layer Monolith" : "Modular Single-app", icon: "🏗️" },
                { title: "Primary Language", val: Object.entries(langMap).sort((a,b) => b[1]-a[1])[0]?.[0] ?? "Unknown", icon: "💻" },
                { title: "Lines of Code", val: totalLoc.toLocaleString(), icon: "📏" },
                { title: "Entry Points", val: `${entryCount} detected`, icon: "🚪" },
              ].map(card => (
                <div key={card.title} className="rounded-lg bg-[#161b22] border border-[#30363d] p-3">
                  <div className="text-base">{card.icon}</div>
                  <div className="text-[10px] text-[#484f58] mt-1">{card.title}</div>
                  <div className="text-sm font-semibold text-[#c9d1d9]">{card.val}</div>
                </div>
              ))}
            </div>
            <div className="rounded-lg bg-[#161b22] border border-[#30363d] p-3">
              <p className="text-[10px] text-[#484f58] mb-1">Most connected files (high centrality)</p>
              <div className="flex flex-wrap gap-1">
                {graph.files.slice(0, 8).map(f => (
                  <span key={f} className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#21262d] text-[#58a6ff]">
                    {f.split("/").pop()}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === "PATTERNS" && (
          <div className="space-y-2">
            {patterns.length === 0 ? (
              <div className="text-center text-[#484f58] py-8 text-sm">✅ No anti-patterns detected</div>
            ) : patterns.map((p, i) => (
              <div key={i} className="rounded-lg p-3 border text-xs"
                style={{ borderColor: SEVERITY_COLORS[p.severity] + "44", background: SEVERITY_BG[p.severity] }}>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-bold" style={{ color: SEVERITY_COLORS[p.severity] }}>{p.type}</span>
                  <span className="font-mono text-[#484f58]">{p.file.split("/").pop()}</span>
                </div>
                <p className="text-[#8b949e]">{p.detail}</p>
              </div>
            ))}
          </div>
        )}

        {activeTab === "SECURITY" && (
          <div className="space-y-2">
            {security.length === 0 ? (
              <div className="text-center text-[#484f58] py-8 text-sm">✅ No security issues found</div>
            ) : (() => {
              const weight: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1, info: 0 };
              const sorted = [...security].sort((a, b) => (weight[b.severity] || 0) - (weight[a.severity] || 0));
              return sorted.map((s, i) => (
                <div key={i} className="rounded-lg p-3 border text-xs font-mono"
                  style={{ borderColor: SEVERITY_COLORS[s.severity] + "44", background: SEVERITY_BG[s.severity] }}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold" style={{ color: SEVERITY_COLORS[s.severity] }}>
                      [{s.severity.toUpperCase()}] {s.type}
                    </span>
                    <span className="text-[#484f58]">{s.file.split("/").pop()}:{s.line}</span>
                  </div>
                  <div className="bg-[#0d1117] p-2 rounded text-[#c9d1d9] my-2 border border-[#30363d] overflow-x-auto">
                    <code>{s.snippet}</code>
                  </div>
                  {s.impact && (
                    <div className="mt-3 text-[#ff7b72] bg-[#161b22] p-2.5 rounded border border-[#da3633]/30">
                      <strong className="text-[#ff7b72] uppercase text-[10px] block mb-1">Impact & Consequences:</strong>
                      <span className="font-sans text-sm block leading-relaxed">{s.impact}</span>
                    </div>
                  )}
                  {s.remediation && (
                    <div className="mt-2 text-[#3fb950] bg-[#161b22] p-2.5 rounded border border-[#3fb950]/30">
                      <strong className="text-[#3fb950] uppercase text-[10px] block mb-1">How to fix (Remediation):</strong>
                      <span className="font-sans text-sm block leading-relaxed">{s.remediation}</span>
                    </div>
                  )}
                </div>
              ));
            })()}
          </div>
        )}

        {activeTab === "ACTIONS" && (
          <div className="space-y-3">
            {graph.action_findings?.map((act, i) => (
              <div key={i} className="rounded-lg p-3 border border-[#30363d] bg-[#161b22] hover:border-[#58a6ff] transition-colors cursor-pointer"
                   onClick={() => onActionSelect && onActionSelect(act)}>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold text-[#c9d1d9]">{act.title}</span>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded uppercase"
                        style={{ color: SEVERITY_COLORS[act.severity], background: SEVERITY_BG[act.severity] }}>
                    {act.severity}
                  </span>
                </div>
                <p className="text-xs text-[#8b949e] mb-2">{act.description}</p>
                <div className="text-xs border-t border-[#30363d] pt-2 mt-2 text-[#484f58] font-mono">
                  Target: {act.target_file.split("/").pop()}
                </div>
              </div>
            ))}

            {claims.filter(c => c.status === "Unverified").map((c, i) => (
              <div key={`u-${i}`} className="rounded-lg p-3 border border-[#da3633]/30 bg-[#da3633]/5 text-xs">
                <p className="font-semibold text-[#ff7b72] mb-1">⚠️ Unverified Claim</p>
                <p className="text-[#c9d1d9]">{c.claim}</p>
                {c.cited_file && (
                  <p className="text-[#484f58] mt-1 font-mono">{c.cited_file}{c.cited_symbol ? `:${c.cited_symbol}` : ""}</p>
                )}
              </div>
            ))}
            
            {actionsCount === 0 && (
               <div className="text-center text-[#484f58] py-8 text-sm">✅ Codebase is perfectly healthy</div>
            )}
          </div>
        )}

        {activeTab === "EXPERTS" && graph.authors && (
          <div className="space-y-4">
            <p className="text-xs text-[#8b949e]">Top contributors mapped to their domains of expertise, based on commit history per file.</p>
            {(() => {
              // Precompute file centrality (how many other files import it)
              const fileCentrality: Record<string, number> = {};
              graph.files.forEach(f => fileCentrality[f] = 0);
              graph.imports?.forEach(imp => {
                const target = graph.files.find(f => f.endsWith(imp.target_module + ".py") || f.endsWith(imp.target_module + ".ts") || f.includes(imp.target_module));
                if (target) {
                  fileCentrality[target] = (fileCentrality[target] || 0) + 1;
                }
              });

              // Build expert map: author -> { files: string[], score: number, centrality: number, soleAuthorFiles: number }
              const experts: Record<string, { files: string[], totalCommits: number, totalCentrality: number, soleAuthorFiles: number }> = {};
              Object.entries(graph.authors).forEach(([file, data]) => {
                const author = data.primary_author;
                if (!experts[author]) experts[author] = { files: [], totalCommits: 0, totalCentrality: 0, soleAuthorFiles: 0 };
                experts[author].files.push(file);
                
                const myCommits = data.authors[author] || 0;
                const totalCommitsForFile = Object.values(data.authors).reduce((a, b) => a + b, 0);
                experts[author].totalCommits += totalCommitsForFile;
                
                const cent = fileCentrality[file] || 0;
                experts[author].totalCentrality += cent;
                
                // If this author wrote >90% of the commits for a file, it's a sole-author file
                if (totalCommitsForFile > 0 && (myCommits / totalCommitsForFile) >= 0.9) {
                   experts[author].soleAuthorFiles += 1;
                }
              });
              
              const sortedExperts = Object.entries(experts)
                .sort((a, b) => b[1].totalCommits - a[1].totalCommits)
                .slice(0, 10);
                
              return sortedExperts.map(([author, data]) => {
                const busFactorRisk = data.totalCentrality > 10 && data.soleAuthorFiles > 5 ? 'High' : data.totalCentrality > 5 ? 'Medium' : 'Low';
                const riskColor = busFactorRisk === 'High' ? '#ff7b72' : busFactorRisk === 'Medium' ? '#d29922' : '#3fb950';
                
                return (
                  <div key={author} className="rounded-lg bg-[#161b22] border border-[#30363d] p-4 overflow-hidden">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                      <div className="flex items-center gap-2 max-w-full">
                        <div className="w-6 h-6 rounded-full bg-[#58a6ff]/20 text-[#58a6ff] flex items-center justify-center font-bold text-xs uppercase flex-shrink-0">
                          {author.slice(0, 2)}
                        </div>
                        <span className="font-bold text-[#c9d1d9] truncate" title={author}>{author}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs font-mono bg-[#0d1117] px-3 py-1.5 rounded-md border border-[#30363d]">
                        <span className="text-[#8b949e]" title="Total commits by this author on their primary files">{data.totalCommits} commits</span>
                        <span className="text-[#58a6ff]" title="Total dependent files relying on this author's code">Centrality: {data.totalCentrality}</span>
                        <span style={{ color: riskColor }} title="Risk of project stall if this author leaves">Risk: {busFactorRisk}</span>
                      </div>
                    </div>
                    <div className="text-xs font-semibold text-[#8b949e] mb-2 uppercase tracking-wider">Domain Expertise</div>
                    <div className="flex flex-wrap gap-1.5">
                      {data.files.slice(0, 8).map(f => (
                        <span key={f} className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#0d1117] border border-[#30363d] text-[#c9d1d9]" title={`${f} (Centrality: ${fileCentrality[f] || 0})`}>
                          {f.split("/").pop()}
                        </span>
                      ))}
                      {data.files.length > 8 && (
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#0d1117] border border-[#30363d] text-[#484f58]">
                          +{data.files.length - 8} more
                        </span>
                      )}
                    </div>
                  </div>
                );
              });
            })()}
          </div>
        )}
      </div>
    </div>
  );

  if (isExpanded) {
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 md:p-8">
        <div className="w-full h-full max-w-[85vw] max-h-[85vh] flex shadow-2xl animate-in fade-in zoom-in-95 duration-200 bg-[#0d1117] rounded-xl border border-[#30363d] overflow-hidden">
          {content}
        </div>
      </div>
    );
  }

  return content;
}
