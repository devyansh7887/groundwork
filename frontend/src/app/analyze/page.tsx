"use client";

import { useState, useEffect, useRef, Suspense, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import mermaid from "mermaid";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";

import { StreamingTerminal } from '@/components/StreamingTerminal';
import { RateLimitModal } from '@/components/RateLimitModal';
import { DiagramCanvas } from '@/components/DiagramCanvas';
import { InsightsPanel } from '@/components/InsightsPanel';
import { ContributionWizard } from '@/components/ContributionWizard';
import { ExplorerPanel } from '@/components/ExplorerPanel';
import { NarrativeSection } from '@/components/NarrativeSection';
import { QASection } from '@/components/QASection';
import { OnboardingSection } from '@/components/OnboardingSection';
import { ContributionDrafter } from '@/components/ContributionDrafter';

mermaid.initialize({ startOnLoad: false, theme: "dark", themeVariables: { fontFamily: "monospace" } });

function Mermaid({ chart }: { chart: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgWrapRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [translate, setTranslate] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [renderError, setRenderError] = useState<string | null>(null);

  useEffect(() => {
    if (!svgWrapRef.current || !chart) return;
    setRenderError(null);
    setScale(1);
    setTranslate({ x: 0, y: 0 });
    const id = "mermaid-" + Math.random().toString(36).substr(2, 9);
    mermaid.render(id, chart).then(({ svg }) => {
      if (svgWrapRef.current) {
        svgWrapRef.current.innerHTML = svg;
        // Make SVG fill its container instead of using fixed dimensions
        const svgEl = svgWrapRef.current.querySelector("svg");
        if (svgEl) {
          svgEl.removeAttribute("width");
          svgEl.removeAttribute("height");
          svgEl.style.width = "100%";
          svgEl.style.height = "100%";
          svgEl.style.display = "block";
        }
      }
    }).catch((e) => {
      setRenderError(e.message);
    });
  }, [chart]);

  const clampScale = (s: number) => Math.min(3, Math.max(0.3, s));

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    // finer step based on direction
    const step = e.deltaY < 0 ? 1.12 : 0.88;
    setScale(prev => clampScale(prev * step));
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX - translate.x, y: e.clientY - translate.y });
  }, [translate]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging) return;
    setTranslate({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  }, [isDragging, dragStart]);

  const handleMouseUp = useCallback(() => setIsDragging(false), []);

  const zoom = (factor: number) => setScale(prev => clampScale(prev * factor));
  const reset = () => { setScale(1); setTranslate({ x: 0, y: 0 }); };

  if (renderError) {
    return (
      <div className="bg-[#0d1117] border border-[#30363d] rounded-md p-4">
        <div className="text-[#da3633] text-sm font-jetbrains mb-2">Failed to render diagram: {renderError}</div>
        <pre className="text-xs overflow-auto text-[#8b949e] font-jetbrains">{chart}</pre>
      </div>
    );
  }

  return (
    <div className="relative">
      {/* Toolbar */}
      <div className="flex items-center gap-2 mb-3">
        <button onClick={() => zoom(1.2)} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#21262d] border border-[#30363d] hover:bg-[#30363d] text-[#c9d1d9] rounded text-xs font-jetbrains transition-colors">
          <span className="w-3.5 h-3.5">[+]</span> Zoom In
        </button>
        <button onClick={() => zoom(0.8)} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#21262d] border border-[#30363d] hover:bg-[#30363d] text-[#c9d1d9] rounded text-xs font-jetbrains transition-colors">
          <span className="w-3.5 h-3.5">[-]</span> Zoom Out
        </button>
        <button onClick={reset} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#21262d] border border-[#30363d] hover:bg-[#30363d] text-[#c9d1d9] rounded text-xs font-jetbrains transition-colors">
          <span className="w-3.5 h-3.5">[^]</span> Reset
        </button>
        <span className="ml-auto text-[#8b949e] text-xs font-jetbrains flex items-center gap-1.5">
          <span className="w-3 h-3">[M]</span> Drag to pan · Scroll to zoom
        </span>
        <span className="text-[#58a6ff] text-xs font-jetbrains bg-[#0d1117] border border-[#30363d] px-2 py-1 rounded">
          {Math.round(scale * 100)}%
        </span>
      </div>

      {/* Viewport */}
      <div
        ref={containerRef}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        className="w-full overflow-hidden rounded-md border border-[#30363d] bg-[#0d1117]"
        style={{ height: "700px", cursor: isDragging ? "grabbing" : "grab" }}
      >
        <div
          ref={svgWrapRef}
          style={{
            transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
            transformOrigin: "top left",
            width: "100%",
            height: "100%",
            transition: isDragging ? "none" : "transform 0.1s ease",
          }}
        />
      </div>
    </div>
  );
}

function AnalyzeContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const repoUrl = searchParams.get("url") || "";
  
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [logs, setLogs] = useState<string[]>([]);
  const [isRateLimitModalOpen, setIsRateLimitModalOpen] = useState(false);
  const [hasShownProactiveRateLimit, setHasShownProactiveRateLimit] = useState(false);
  const [sessionToken, setSessionToken] = useState("");
  const [mode, setMode] = useState(searchParams.get("mode") || "technical");
  const [backendReady, setBackendReady] = useState(false);
  
  // Results
  const [readme, setReadme] = useState("");
  const [diagram, setDiagram] = useState("");
  const [claims, setClaims] = useState<Array<{ claim: string; status: string; cited_file: string; cited_symbol?: string }>>([]);
  const [graphData, setGraphData] = useState<any>(null);
  const [fileSizes, setFileSizes] = useState<Record<string, number>>({});
  const [fileLocs, setFileLocs] = useState<Record<string, number>>({});
  const [security, setSecurity] = useState<any[]>([]);
  const [patterns, setPatterns] = useState<any[]>([]);
  const [driftInfo, setDriftInfo] = useState<{ stale: boolean; cached_sha: string; current_sha: string } | null>(null);
  const [activeResultTab, setActiveResultTab] = useState<"narrative" | "diagram" | "wizard" | "qa" | "onboarding" | "issues">("narrative");
  
  // Q&A
  const [question, setQuestion] = useState("");
  const [qaHistory, setQaHistory] = useState<Array<{ q: string; a: string; claims?: Array<{ claim: string; status: string; cited_file: string }> }>>([]);
  const [asking, setAsking] = useState(false);
  const [qaError, setQaError] = useState("");
  const [isQaMinimized, setIsQaMinimized] = useState(false);
  
  // Onboarding
  const [role, setRole] = useState("full-stack");
  const [level, setLevel] = useState("beginner");
  const [path, setPath] = useState<{ path: Array<{ file_path: string; rationale: string; concepts: string[] }> } | null>(null);
  const [pathLoading, setPathLoading] = useState(false);
  const [pathError, setPathError] = useState("");
  
  // Contribution
  const [draft, setDraft] = useState<{ message?: string; issue_title?: string; target_file?: string; diff?: string; test_code?: string; pr_description?: string } | null>(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [draftError, setDraftError] = useState("");
  const [selectedAction, setSelectedAction] = useState<any>(null);
  
  // Diagram Views
  const [colorBy, setColorBy] = useState<"folder" | "type" | "author">("folder");

  const hasFetched = useRef(false);

  useEffect(() => {
    if (repoUrl && status === "idle" && !hasFetched.current && backendReady) {
      hasFetched.current = true;
      handleAnalyze(repoUrl);
    }
  }, [repoUrl, status, backendReady]);

  // Health check polling
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/health`);
        if (res.ok) {
          setBackendReady(true);
        }
      } catch (e) {
        setBackendReady(false);
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 2000);
    return () => clearInterval(interval);
  }, []);

  // Proactively check rate limit every 15s
  useEffect(() => {
    if (hasShownProactiveRateLimit || isRateLimitModalOpen || status !== "loading") return;
    
    const checkStatus = async () => {
      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/key-status`);
        if (res.ok) {
          const data = await res.json();
          const totalRemaining = data.keys.reduce((acc: number, k: any) => acc + (k.remaining === -1 ? 5000 : k.remaining), 0);
          if (totalRemaining > 0 && totalRemaining < 10) {
            setIsRateLimitModalOpen(true);
            setHasShownProactiveRateLimit(true);
          }
        }
      } catch (e) {}
    };

    const interval = setInterval(checkStatus, 15000);
    return () => clearInterval(interval);
  }, [hasShownProactiveRateLimit, isRateLimitModalOpen, status]);
  
  const handleModeChange = async (newMode: string) => {
    if (newMode === mode) return;
    setMode(newMode);
    router.replace(`/analyze?url=${encodeURIComponent(repoUrl)}&mode=${newMode}`);
    
    // If we have results already, use the fast resynthesize endpoint (no GitHub calls)
    if (status === "success") {
      setStatus("loading");
      setLogs([`  Switching to ${newMode === 'eli5' ? 'ELI5' : newMode === 'tldr' ? 'TLDR' : 'Technical'} mode...`]);
      try {
        const headers: any = { "Content-Type": "application/json" };
        if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/resynthesize`, {
          method: "POST",
          headers,
          body: JSON.stringify({ repo_url: repoUrl, mode: newMode })
        });
        if (!res.ok) {
          // Cache miss - fall back to full analysis
          handleAnalyze(repoUrl, sessionToken, newMode);
          return;
        }
        const data = await res.json();
        const cleanReadme = data.readme.replace(/```mermaid[\s\S]*?```/g, '');
        setReadme(cleanReadme);
        setClaims(data.claims || []);
        setStatus("success");
        setLogs([`  Mode switched to ${newMode}`]);
      } catch (err) {
        // Fallback to full analysis on error
        handleAnalyze(repoUrl, sessionToken, newMode);
      }
      return;
    }
    
    // If idle or error, do full analysis
    if (status !== "loading") {
      handleAnalyze(repoUrl, sessionToken, newMode);
    }
  };

  const handleAnalyze = async (url: string, tokenToUse?: string, modeToUse?: string, forceRefresh: boolean = false) => {
    // Reset previous results to avoid stale cached data
    setReadme("");
    setDiagram("");
    setClaims([]);
    setGraphData(null);
    setFileSizes({});
    setSecurity([]);
    setPatterns([]);
    setDriftInfo(null);
    setLogs([]);
    setStatus("loading");
    setErrorMsg("");

    try {
      const headers: any = { "Content-Type": "application/json" };
      const activeToken = tokenToUse || sessionToken;
      if (activeToken) headers["Authorization"] = `Bearer ${activeToken}`;

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/analyze`, {
        method: "POST",
        headers,
        body: JSON.stringify({ repo_url: url, mode: modeToUse || mode, force_refresh: forceRefresh })
      });
      
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        const errMsg = errorData.detail || "Failed to analyze repository";
        if (errMsg.toLowerCase().includes("rate limit")) {
          setIsRateLimitModalOpen(true);
        }
        throw new Error(errMsg);
      }
      
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error("No response stream");

      let buffer = "";
      let receivedResult = false;
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          if (!receivedResult) {
            throw new Error("Connection dropped by the server before finishing (this usually means the API timed out or the repository is too large). Please try again or analyze a smaller repository.");
          }
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        
        let boundary = buffer.indexOf('\n\n');
        while (boundary !== -1) {
          const chunk = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          
          if (chunk.startsWith('data: ')) {
            const dataStr = chunk.slice(6);
            if (dataStr) {
              try {
                const parsed = JSON.parse(dataStr);
                    if (parsed.log) {
                       setLogs(prev => {
                         if (prev.length > 0 && prev[prev.length - 1] === parsed.log) return prev;
                         return [...prev, parsed.log];
                       });
                    } else if (parsed.result) {
                   const cleanReadme = parsed.result.readme.replace(/```mermaid[\s\S]*?```/g, '');
                   setReadme(cleanReadme);
                   setDiagram(parsed.result.diagram || "");
                   setClaims(parsed.result.claims || []);
                   setGraphData(parsed.result.graph || null);
                   setFileSizes(parsed.result.file_sizes || {});
                   setFileLocs(parsed.result.file_locs || {});
                   setSecurity(parsed.result.security || []);
                   setPatterns(parsed.result.patterns || []);
                   receivedResult = true;
                   if (parsed.result.from_cache) {
                     setLogs(prev => [...prev, "  Loaded from cache - instant results!"]);
                   }
                   setStatus("success");
                   // Check for drift after loading
                   fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/drift?repo_url=${encodeURIComponent(url)}`)
                     .then(r => r.ok ? r.json() : null)
                     .then(d => { if (d?.stale) setDriftInfo(d); })
                     .catch(() => {});
                } else if (parsed.error) {
                   throw new Error(parsed.error);
                }
              } catch (e: any) {
                if (e.message && e.message !== "Unexpected end of JSON input" && !e.message.includes("JSON")) {
                   throw e;
                }
                console.error("Failed to parse SSE chunk", e);
              }
            }
          }
          boundary = buffer.indexOf('\n\n');
        }
      }
    } catch (err: unknown) {
      setStatus("error");
      setErrorMsg(err instanceof Error ? err.message : String(err));
    }
  };

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question || asking) return;
    
    setAsking(true);
    setQaError("");
    try {
      const headers: any = { "Content-Type": "application/json" };
      if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/qa`, {
        method: "POST",
        headers,
        body: JSON.stringify({ repo_url: repoUrl, question })
      });
      
      const data = await res.json();
      if (data.error || data.detail) {
        throw new Error(data.error || data.detail);
      }
      setQaHistory([...qaHistory, { q: question, a: data.answer, claims: data.claims }]);
      setQuestion("");
    } catch (err: unknown) {
      setQaError("Error asking question: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setAsking(false);
    }
  };

  const handleGeneratePath = async () => {
    setPathLoading(true);
    setPathError("");
    try {
      const headers: any = { "Content-Type": "application/json" };
      if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/onboard`, {
        method: "POST",
        headers,
        body: JSON.stringify({ repo_url: repoUrl, role, level })
      });
      setPath(await res.json());
    } catch (err: unknown) {
      setPathError("Error generating path: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setPathLoading(false);
    }
  };

  const handleDraft = async () => {
    setDraftLoading(true);
    setDraftError("");
    try {
      const headers: any = { "Content-Type": "application/json" };
      if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/draft`, {
        method: "POST",
        headers,
        body: JSON.stringify({ repo_url: repoUrl })
      });
      setDraft(await res.json());
    } catch (err: unknown) {
      setDraftError("Error drafting contribution: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setDraftLoading(false);
    }
  };

  const Badge = ({ status }: { status: string }) => {
    if (status === "Verified") return <span className="inline-flex items-center px-2 py-1 rounded-[4px] text-xs font-jetbrains font-bold bg-green-500/10 text-green-400 border border-green-500/30"><span className="w-3 h-3 mr-1">[+]</span> VERIFIED</span>;
    if (status === "Inferred") return <span className="inline-flex items-center px-2 py-1 rounded-[4px] text-xs font-jetbrains font-bold bg-yellow-500/10 text-yellow-400 border border-yellow-500/30"><span className="w-3 h-3 mr-1">[?]</span> INFERRED</span>;
    return <span className="inline-flex items-center px-2 py-1 rounded-[4px] text-xs font-jetbrains font-bold bg-red-500/10 text-red-400 border border-red-500/30"><span className="w-3 h-3 mr-1">[x]</span> UNVERIFIED</span>;
  };

  const CitationChip = ({ text }: { text: string }) => {
    return (
      <span 
        onClick={() => navigator.clipboard.writeText(text)}
        className="inline-flex items-center gap-1 bg-[#0d1117] border border-[#30363d] text-[#58a6ff] font-jetbrains text-[11px] px-2 py-0.5 rounded-[4px] mx-1 cursor-pointer hover:bg-[#161b22] hover:border-[#8b949e] transition-colors relative -top-0.5"
        title="Copy path"
      >
        {text} <span className="w-3 h-3 opacity-70">[c]</span>
      </span>
    );
  };

  if (status === "loading" || (status === "idle" && !backendReady && repoUrl)) {
    return (
      <>
        {!backendReady && (
          <div className="absolute top-4 left-1/2 transform -translate-x-1/2 bg-[#161b22] border border-[#d29922] text-[#d29922] px-4 py-2 rounded-full text-xs font-jetbrains font-bold flex items-center z-50 shadow-lg">
            <span className="w-3.5 h-3.5 border-2 border-[#d29922] border-t-transparent rounded-full animate-spin mr-2.5" /> 
            Backend warming up...
          </div>
        )}
        <StreamingTerminal logs={logs} />
        <RateLimitModal 
          isOpen={isRateLimitModalOpen} 
          onClose={() => setIsRateLimitModalOpen(false)} 
          onSubmit={(token) => {
            setSessionToken(token);
            setIsRateLimitModalOpen(false);
            handleAnalyze(repoUrl, token);
          }} 
        />
      </>
    );
  }

  if (status === "error") {
    return (
      <>
        <div className="max-w-3xl mx-auto mt-20 p-6 bg-[#161b22] border border-[#da3633] rounded-md">
          <h2 className="font-space text-[#da3633] font-jetbrains text-xl font-bold mb-4 flex items-center">
            <span className="mr-3">[x]</span> ERR_ANALYSIS_FAILED
          </h2>
          <pre className="text-[#8b949e] font-jetbrains text-sm bg-[#0d1117] p-4 border border-[#30363d] rounded whitespace-pre-wrap">
            {errorMsg}
          </pre>
          <div className="mt-6 flex items-center gap-4">
            <Link href="/" className="inline-flex items-center text-[#8b949e] hover:text-[#c9d1d9] transition-colors font-jetbrains text-sm">
              <span className="w-4 h-4 mr-2">«</span> Return to input
            </Link>
            <button 
              onClick={() => handleAnalyze(repoUrl)}
              className="inline-flex items-center px-4 py-2 bg-[#21262d] text-[#c9d1d9] border border-[#30363d] rounded-md hover:bg-[#30363d] transition-colors font-jetbrains text-sm font-bold"
            >
              Retry Analysis
            </button>
          </div>
        </div>
        <RateLimitModal 
          isOpen={isRateLimitModalOpen} 
          onClose={() => setIsRateLimitModalOpen(false)} 
          onSubmit={(token) => {
            setSessionToken(token);
            setIsRateLimitModalOpen(false);
            handleAnalyze(repoUrl, token);
          }} 
        />
      </>
    );
  }

  return (
    <div className="w-full h-screen flex flex-col bg-[#0d1117]">
      <div className="flex-none flex items-center justify-between bg-[#161b22] border-b border-[#30363d] px-4 py-3 z-10">
        <div>
          <Link href="/" className="inline-flex items-center text-[#8b949e] hover:text-[#58a6ff] font-jetbrains text-xs mb-4 uppercase tracking-wider transition-colors">
            <span className="w-3 h-3 mr-1">«</span> New Analysis
          </Link>
          <h1 className="font-space text-2xl font-bold text-[#c9d1d9] flex items-center tracking-tight">
            <span className="w-6 h-6 mr-3 text-[#8b949e]">|-</span>
            {repoUrl.replace("https://github.com/", "")}
          </h1>
        </div>
        <div className="mt-4 md:mt-0 font-jetbrains text-xs text-[#8b949e] flex items-center bg-[#0d1117] px-3 py-1.5 rounded border border-[#30363d]">
          <span className="w-2 h-2 rounded-full bg-[#238636] mr-2 shadow-[0_0_8px_rgba(35,134,54,0.6)]"></span> STATIC_ANALYSIS_COMPLETE
        </div>
      </div>

      {/* Drift Alert Banner */}
      {driftInfo && driftInfo.stale && (
        <div className="flex-none flex items-center justify-between bg-[#d29922] border-b border-[#d29922]/40 px-4 py-2 text-[#d29922]">
          <div className="flex items-center gap-3">
            <span className="text-xl"></span>
            <div>
              <h3 className="font-space font-bold text-sm">Repository Drift Detected</h3>
              <p className="text-xs text-[#d29922]/80 mt-0.5">
                New commits have been pushed since this analysis was generated.
              </p>
            </div>
          </div>
          <button 
            onClick={() => handleAnalyze(repoUrl, sessionToken, mode, true)}
            className="px-4 py-1.5 bg-[#d29922] hover:bg-[#d29922] border border-[#d29922]/50 text-[#d29922] font-semibold text-xs rounded transition-colors"
          >
            Re-analyze
          </button>
        </div>
      )}

      <div className="max-w-[90rem] mx-auto w-full h-[calc(100vh-57px)] p-4 overflow-y-auto xl:overflow-hidden">
        <div className="flex flex-col xl:flex-row gap-4 h-full">
        
        {/* Left Column: Explorer (Codeflow style) */}
        {graphData && (
          <div className="w-[300px] flex-none hidden lg:block">
            <ExplorerPanel 
              graph={graphData} 
              fileSizes={fileSizes} 
              colorBy={colorBy} 
              onColorByChange={setColorBy} 
            />
          </div>
        )}

        {/* Center Column: Docs & Diagrams */}
        <div className="flex-1 flex flex-col overflow-y-auto p-4 space-y-4">
          
          {/* Analysis Mode Toggle */}
          <div className="flex items-center gap-2 bg-[#161b22] border border-[#30363d] p-1 rounded-full w-fit">
             <button onClick={() => handleModeChange("technical")} className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-colors ${mode === "technical" ? "bg-[#30363d] text-white" : "text-[#8b949e] hover:text-[#c9d1d9]"}`}> Technical</button>
             <button onClick={() => handleModeChange("eli5")} className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-colors ${mode === "eli5" ? "bg-[#30363d] text-white" : "text-[#8b949e] hover:text-[#c9d1d9]"}`}> ELI5</button>
             <button onClick={() => handleModeChange("tldr")} className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-colors ${mode === "tldr" ? "bg-[#30363d] text-white" : "text-[#8b949e] hover:text-[#c9d1d9]"}`}> TLDR</button>
          </div>

          {/* Result Segmented Control */}
          <div className="flex bg-[#161b22] border border-[#30363d] rounded-lg p-1 w-full max-w-2xl mx-auto">
            <button 
              onClick={() => setActiveResultTab("narrative")} 
              className={`flex-1 py-2 px-4 rounded-md text-sm font-bold flex items-center justify-center gap-2 transition-all ${
                activeResultTab === "narrative" 
                  ? "bg-[#21262d] text-[#c9d1d9]  border border-[#30363d]" 
                  : "text-[#8b949e] hover:text-[#c9d1d9] border border-transparent"
              }`}
            >
               Architecture Narrative
            </button>
            <button 
              onClick={() => setActiveResultTab("diagram")} 
              className={`flex-1 py-2 px-4 rounded-md text-sm font-bold flex items-center justify-center gap-2 transition-all ${
                activeResultTab === "diagram" 
                  ? "bg-[#21262d] text-[#58a6ff]  border border-[#30363d]" 
                  : "text-[#8b949e] hover:text-[#58a6ff] border border-transparent"
              }`}
            >
               Component Diagram
            </button>
            <button 
              onClick={() => setActiveResultTab("wizard")} 
              className={`flex-1 py-2 px-3 rounded-md text-sm font-bold flex items-center justify-center gap-1.5 transition-all ${
                activeResultTab === "wizard" 
                  ? "bg-[#21262d] text-[#3fb950]  border border-[#30363d]" 
                  : "text-[#8b949e] hover:text-[#3fb950] border border-transparent"
              }`}
            >
               Mentor
            </button>
            <button 
              onClick={() => setActiveResultTab("qa")} 
              className={`flex-1 py-2 px-3 rounded-md text-sm font-bold flex items-center justify-center gap-1.5 transition-all ${
                activeResultTab === "qa" 
                  ? "bg-[#21262d] text-[#a371f7]  border border-[#30363d]" 
                  : "text-[#8b949e] hover:text-[#a371f7] border border-transparent"
              }`}
            >
               Q&A
            </button>
            <button 
              onClick={() => setActiveResultTab("issues")} 
              className={`flex-1 py-2 px-3 rounded-md text-sm font-bold flex items-center justify-center gap-1.5 transition-all ${
                activeResultTab === "issues" 
                  ? "bg-[#21262d] text-[#238636]  border border-[#30363d]" 
                  : "text-[#8b949e] hover:text-[#238636] border border-transparent"
              }`}
            >
               Issues & Contribute
            </button>
          </div>

          {/* Architecture Narrative */}
          {activeResultTab === "narrative" && (
            <NarrativeSection readme={readme} />
          )}

          {/* Diagram Canvas */}
          {activeResultTab === "diagram" && diagram && graphData && (
            <section className="bg-[#161b22] border border-[#30363d] rounded-md p-6 mt-2">
              <DiagramCanvas 
                mermaidChart={diagram} 
                graph={graphData} 
                fileSizes={fileSizes} 
                colorBy={colorBy}
              />
            </section>
          )}

          {/* Contribution Wizard Tab */}
          {activeResultTab === "wizard" && (
            <div className="flex-1 w-full mt-2">
              {!selectedAction ? (
                <div className="flex flex-col items-center justify-center h-[500px] bg-[#161b22] border border-[#30363d] rounded-md text-center p-8">
                  <div className="text-6xl mb-6"></div>
                  <h3 className="font-space text-2xl font-bold text-[#c9d1d9] mb-4">Contribution Mentor</h3>
                  <p className="text-[#8b949e] max-w-md text-lg leading-relaxed">
                    Ready to make an impact? To begin, select any specific issue from the <strong className="text-[#c9d1d9]"> ACTIONS</strong> tab in the right-hand Insights Panel.
                  </p>
                  <p className="text-[#8b949e] max-w-md text-lg leading-relaxed mt-4">
                    The Contribution Mentor will then automatically generate a draft PR, step-by-step guidance, and relevant codebase context to help you solve it!
                  </p>
                </div>
              ) : (
                <ContributionWizard 
                  repoUrl={repoUrl}
                  action={selectedAction}
                  onDraftRequest={async (act) => {
                    setDraftLoading(true);
                    try {
                      const headers: any = { "Content-Type": "application/json" };
                      if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;
                      
                      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/draft`, {
                        method: "POST",
                        headers,
                        body: JSON.stringify({ repo_url: repoUrl, action: act })
                      });
                      if (!res.ok) throw new Error("Failed to draft patch");
                      return await res.json();
                    } catch (err) {
                      console.error(err);
                      return null;
                    } finally {
                      setDraftLoading(false);
                    }
                  }} 
                />
              )}
            </div>
          )}

          {/* Q&A Tab */}
          {activeResultTab === "qa" && (
            <QASection 
              qaHistory={qaHistory}
              asking={asking}
              qaError={qaError}
              question={question}
              setQuestion={setQuestion}
              setQaError={setQaError}
              handleAsk={handleAsk}
            />
          )}

          {/* Contribution Drafter Tab */}
          {activeResultTab === "issues" && (
            <div className="h-[600px] xl:h-full w-full">
              <ContributionDrafter 
                repoUrl={repoUrl}
                sessionToken={sessionToken}
              />
            </div>
          )}

        </div>

        {/* Right Column: Insights & Q&A */}
        <div className="w-full xl:w-[380px] flex-none flex flex-col border-l border-[#30363d] bg-[#0d1117] overflow-y-auto p-4 space-y-4">
          
          {/* Insights Panel */}
          {graphData && (
            <InsightsPanel 
              graph={graphData} 
              fileSizes={fileSizes} 
              fileLocs={fileLocs}
              claims={claims} 
              readme={readme} 
              security={security} 
              patterns={patterns} 
              onActionSelect={(act) => {
                setSelectedAction(act);
                setActiveResultTab("wizard");
              }}
            />
          )}
          
          {/* Removed Grounded Q&A from right panel */}

          {/* Onboarding Path */}
          <OnboardingSection 
            role={role}
            setRole={setRole}
            level={level}
            setLevel={setLevel}
            pathLoading={pathLoading}
            pathError={pathError}
            setPathError={setPathError}
            path={path}
            handleGeneratePath={handleGeneratePath}
          />

        </div>
      </div>
    </div>
    </div>
  );
}

export default function AnalyzePage() {
  return (
    <div className="min-h-screen bg-[#0d1117] text-[#c9d1d9] font-ibm">
      <header className="border-b border-[#30363d] bg-[#161b22] sticky top-0 z-50">
        <div className="max-w-[90rem] mx-auto px-4 py-3 flex items-center">
          <Link href="/" className="w-8 h-8 bg-[#0d1117] border border-[#30363d] rounded flex items-center justify-center mr-3 hover:bg-[#21262d] transition-colors">
            <span className="text-[#c9d1d9] font-jetbrains font-bold text-sm leading-none mt-0.5">&gt;_</span>
          </Link>
          <div>
            <h1 className="font-space text-lg font-bold text-[#c9d1d9] tracking-tight leading-none">Groundwork</h1>
            <p className="text-[10px] font-jetbrains text-[#8b949e] mt-1">VERIFIABLE_CODEBASE_AGENT</p>
          </div>
        </div>
      </header>
      
      <Suspense fallback={
        <div className="flex items-center justify-center min-h-[70vh]">
          <span className="w-8 h-8 animate-spin text-[#8b949e]">...</span>
        </div>
      }>
        <AnalyzeContent />
      </Suspense>
    </div>
  );
}
