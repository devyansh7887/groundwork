"use client";

import React, { useState, useEffect } from "react";
import { MessageSquare, GitPullRequest, Terminal, Maximize2, Minimize2, Loader2, Play } from "lucide-react";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Issue {
  number: number;
  title: string;
  body: string;
  author: string;
  state: string;
  labels: string[];
}

export function ContributionDrafter({ repoUrl, sessionToken }: { repoUrl: string, sessionToken: string | null }) {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [isMaximized, setIsMaximized] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [draftResult, setDraftResult] = useState<any>(null);

  useEffect(() => {
    fetchIssues();
  }, [repoUrl]);

  const fetchIssues = async () => {
    setLoading(true);
    setError("");
    try {
      const headers: any = { "Content-Type": "application/json" };
      if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;

      const res = await fetch(`https://groundwork-api-6bnh.onrender.com/api/issues`, {
        method: "POST",
        headers,
        body: JSON.stringify({ repo_url: repoUrl })
      });
      if (!res.ok) throw new Error("Failed to fetch issues");
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setIssues(data.issues || []);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDraft = async (issue: Issue) => {
    setDrafting(true);
    setDraftResult(null);
    try {
      const headers: any = { "Content-Type": "application/json" };
      if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;

      const res = await fetch(`https://groundwork-api-6bnh.onrender.com/api/draft`, {
        method: "POST",
        headers,
        body: JSON.stringify({ repo_url: repoUrl, issue })
      });
      if (!res.ok) throw new Error("Failed to draft contribution");
      const data = await res.json();
      setDraftResult(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDrafting(false);
    }
  };

  const containerClasses = isMaximized 
    ? "fixed inset-4 z-50 bg-[#0d1117] border border-[#30363d] rounded-xl shadow-2xl flex flex-col overflow-hidden" 
    : "w-full h-full bg-[#0d1117] border border-[#30363d] rounded-xl flex flex-col overflow-hidden shadow-inner relative";

  return (
    <div className={containerClasses}>
      {/* Header bar - GitHub/Terminal hybrid style */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#30363d] bg-[#161b22] text-[#8b949e] font-mono text-xs">
        <div className="flex items-center gap-2">
          <Terminal size={14} className="text-[#58a6ff]" />
          <span className="text-[#c9d1d9]">groundwork/contribution-drafter <span className="text-[#58a6ff]">~</span></span>
        </div>
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500"></span> Online</span>
          <button onClick={() => setIsMaximized(!isMaximized)} className="hover:text-white transition-colors">
            {isMaximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left pane: Issues List */}
        <div className="w-1/3 border-r border-[#30363d] bg-[#0d1117] flex flex-col">
          <div className="p-3 border-b border-[#30363d] bg-[#161b22]/50 font-semibold text-[#c9d1d9] flex justify-between items-center text-sm">
            <span>Open Issues</span>
            <span className="px-2 py-0.5 rounded-full bg-[#238636]/20 text-[#238636] text-xs font-mono">{issues.length}</span>
          </div>
          <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-2">
            {loading && <div className="text-[#8b949e] p-4 text-center text-sm animate-pulse flex items-center justify-center gap-2"><Loader2 size={14} className="animate-spin" /> Fetching issues...</div>}
            {error && <div className="text-red-400 p-4 text-xs font-mono bg-red-500/10 rounded">{error}</div>}
            {!loading && issues.length === 0 && !error && <div className="text-[#8b949e] p-4 text-center text-sm">No issues found.</div>}
            {issues.map(issue => (
              <div 
                key={issue.number}
                onClick={() => { setSelectedIssue(issue); setDraftResult(null); }}
                className={`p-3 rounded-lg border cursor-pointer transition-all ${
                  selectedIssue?.number === issue.number 
                    ? 'border-[#58a6ff] bg-[#1f6feb]/10 shadow-[0_0_10px_rgba(88,166,255,0.1)]' 
                    : 'border-[#30363d] bg-[#161b22] hover:border-[#8b949e] hover:bg-[#21262d]'
                }`}
              >
                <div className="flex items-start gap-2">
                  <MessageSquare size={14} className="text-[#238636] mt-1 shrink-0" />
                  <div>
                    <h4 className="text-sm font-semibold text-[#c9d1d9] line-clamp-2 leading-snug">{issue.title}</h4>
                    <p className="text-xs text-[#8b949e] mt-1 font-mono">#{issue.number} opened by {issue.author}</p>
                    {issue.labels && issue.labels.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {issue.labels.slice(0,3).map((l, i) => {
                          const labelText = typeof l === 'string' ? l : (l as any).name || 'label';
                          return (
                            <span key={i} className="px-1.5 py-0.5 rounded-full border border-[#30363d] text-[10px] text-[#8b949e] bg-[#0d1117]">
                              {labelText}
                            </span>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right pane: Draft Area */}
        <div className="w-2/3 bg-[#0d1117] flex flex-col">
          {!selectedIssue ? (
            <div className="flex-1 flex flex-col items-center justify-center text-[#8b949e] font-mono text-sm">
              <GitPullRequest size={32} className="mb-4 opacity-50" />
              <p>Select an issue to draft a contribution</p>
            </div>
          ) : (
            <>
              {/* Issue Details Header */}
              <div className="p-4 border-b border-[#30363d] bg-[#161b22] shrink-0">
                <h2 className="text-xl font-semibold text-[#c9d1d9] mb-2">{selectedIssue.title} <span className="text-[#8b949e] font-mono font-normal">#{selectedIssue.number}</span></h2>
                <div className="flex justify-between items-center">
                  <div className="prose prose-invert prose-sm max-w-none text-[#8b949e] line-clamp-2">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{selectedIssue.body || "*No description provided*"}</ReactMarkdown>
                  </div>
                  <button 
                    onClick={() => handleDraft(selectedIssue)}
                    disabled={drafting}
                    className="ml-4 shrink-0 px-4 py-2 bg-[#238636] hover:bg-[#2ea043] disabled:opacity-50 text-white text-sm font-semibold rounded-md shadow-sm transition-colors flex items-center gap-2"
                  >
                    {drafting ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
                    {drafting ? "Drafting..." : "Auto Draft PR"}
                  </button>
                </div>
              </div>

              {/* Draft Results */}
              <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                {!draftResult && !drafting && (
                  <div className="h-full flex items-center justify-center text-[#8b949e] font-mono text-xs text-center p-8">
                    <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-6 max-w-md">
                      <Terminal size={24} className="mx-auto mb-3 text-[#58a6ff]" />
                      <p className="mb-2 text-[#c9d1d9] font-semibold">Ready to draft</p>
                      <p>Click "Auto Draft PR" to let the AI analyze this issue and write the necessary code patches to fix it.</p>
                    </div>
                  </div>
                )}
                
                {drafting && (
                  <div className="font-mono text-sm text-[#8b949e] p-4 space-y-2">
                    <div className="flex items-center gap-2 text-[#58a6ff]"><Loader2 size={14} className="animate-spin" /> Analyzing codebase context...</div>
                    <div className="text-xs pl-5 opacity-70">Reviewing central nodes & related files</div>
                  </div>
                )}

                {draftResult && (
                  <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                    <div className="bg-[#161b22] border border-[#30363d] rounded-lg overflow-hidden">
                      <div className="px-4 py-2 bg-[#21262d] border-b border-[#30363d] text-xs font-mono font-semibold text-[#c9d1d9] flex justify-between">
                        <span>Proposed Patch ({draftResult.target_file})</span>
                        <span className="text-[#8b949e]">git diff</span>
                      </div>
                      <pre className="p-4 text-xs font-mono text-gray-300 overflow-x-auto">
                        <code dangerouslySetInnerHTML={{ __html: draftResult.diff.replace(/^\+.*$/gm, '<span class="text-green-400">$&</span>').replace(/^-.*$/gm, '<span class="text-red-400">$&</span>') }} />
                      </pre>
                    </div>
                    
                    <div className="bg-[#161b22] border border-[#30363d] rounded-lg overflow-hidden">
                      <div className="px-4 py-2 bg-[#21262d] border-b border-[#30363d] text-xs font-mono font-semibold text-[#c9d1d9]">
                        PR Description
                      </div>
                      <div className="p-4 text-sm text-[#8b949e] prose prose-invert max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{draftResult.pr_description}</ReactMarkdown>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
