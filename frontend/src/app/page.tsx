"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";

export default function Home() {
  const [repoUrl, setRepoUrl] = useState("");
  const [mode, setMode] = useState("technical");
  const router = useRouter();

  const handleAnalyze = (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl) return;
    
    // Navigate to the analysis page
    router.push(`/analyze?url=${encodeURIComponent(repoUrl)}&mode=${mode}`);
  };

  return (
    <div className="min-h-screen bg-[#0d1117] text-[#c9d1d9] font-ibm selection:bg-[#58a6ff] flex flex-col">
      <header className="border-b border-[#30363d] bg-[#161b22] sticky top-0 z-50">
        <div className="max-w-[90rem] mx-auto px-4 py-3 flex items-center">
          <div className="w-8 h-8 bg-[#0d1117] border border-[#30363d] rounded flex items-center justify-center mr-3">
            <span className="text-[#c9d1d9] font-jetbrains font-bold text-sm leading-none mt-0.5">&gt;_</span>
          </div>
          <div>
            <h1 className="font-space text-lg font-bold text-[#c9d1d9] tracking-tight leading-none">Groundwork</h1>
            <p className="text-[10px] font-jetbrains text-[#8b949e] mt-1">VERIFIABLE_CODEBASE_AGENT</p>
          </div>
        </div>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center px-4 overflow-y-auto pb-10 pt-10">
        <motion.div 
          initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
          className="text-center mb-12"
        >
          <div className="w-20 h-20 bg-[#161b22] border border-[#30363d] shadow-[#0d1117] rounded-xl flex items-center justify-center mx-auto mb-6">
            <span className="text-[#c9d1d9] font-jetbrains font-bold text-3xl leading-none mt-1">&gt;_</span>
          </div>
          <h2 className="font-space text-4xl md:text-5xl font-bold mb-4 text-[#c9d1d9] tracking-tight">Verify what your codebase actually does.</h2>
          <p className="text-lg text-[#8b949e] font-jetbrains max-w-2xl mx-auto">
            Grounded architecture analysis mapped directly to AST graphs.
          </p>
        </motion.div>

        <motion.div 
          initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          className="w-full max-w-2xl bg-[#161b22] border border-[#30363d] p-8 rounded-lg"
        >
          <form onSubmit={handleAnalyze} className="flex flex-col gap-4">
            <label className="text-sm font-bold text-[#c9d1d9] mb-1">Target Repository URL</label>
            <div className="relative group">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                <span className="h-5 w-5 text-[#8b949e] group-focus-within:text-[#58a6ff] transition-colors">[?]</span>
              </div>
              <input
                type="url"
                className="block w-full pl-12 pr-4 py-4 bg-[#0d1117] border border-[#30363d] rounded-md focus:ring-1 focus:ring-[#58a6ff] focus:border-[#58a6ff] text-[#c9d1d9] placeholder-[#8b949e] font-jetbrains text-sm outline-none transition-shadow"
                placeholder="https://github.com/owner/repo"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                required
              />
            </div>
            
            <div className="mt-2">
              <label className="text-sm font-bold text-[#c9d1d9] mb-2 block">Analysis Mode</label>
              <div className="flex items-center gap-2 bg-[#0d1117] border border-[#30363d] p-1 rounded-md w-fit">
                <button type="button" onClick={() => setMode("technical")} className={`px-4 py-2 rounded text-sm font-semibold transition-colors ${mode === "technical" ? "bg-[#21262d] text-white border border-[#30363d]" : "text-[#8b949e] hover:text-[#c9d1d9]"}`}> Technical</button>
                <button type="button" onClick={() => setMode("eli5")} className={`px-4 py-2 rounded text-sm font-semibold transition-colors ${mode === "eli5" ? "bg-[#21262d] text-white border border-[#30363d]" : "text-[#8b949e] hover:text-[#c9d1d9]"}`}> ELI5</button>
                <button type="button" onClick={() => setMode("tldr")} className={`px-4 py-2 rounded text-sm font-semibold transition-colors ${mode === "tldr" ? "bg-[#21262d] text-white border border-[#30363d]" : "text-[#8b949e] hover:text-[#c9d1d9]"}`}> TLDR</button>
              </div>
            </div>
            
            <div className="flex justify-between items-center mt-4">
              <div className="text-[11px] font-jetbrains text-[#8b949e]">
                <span className="text-[#238636]">✓</span> Requires public repository
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    setRepoUrl("https://github.com/encode/starlette");
                    setMode("technical");
                    router.push(`/analyze?url=${encodeURIComponent("https://github.com/encode/starlette")}&mode=technical`);
                  }}
                  className="px-6 py-3 rounded-md font-bold font-ibm text-[#c9d1d9] bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] transition-colors flex items-center"
                >
                  Try a Demo
                </button>
                <button
                  type="submit"
                  className="px-6 py-3 rounded-md font-bold font-ibm text-white bg-[#238636] hover:bg-[#2ea043] border border-[rgba(240,246,252,0.1)] transition-colors flex items-center"
                >
                  Run Analysis
                </button>
              </div>
            </div>
          </form>
        </motion.div>
        
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="w-full max-w-5xl mt-16">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-[#161b22] border border-[#30363d] p-6 rounded-lg text-center">
              <div className="text-3xl font-black text-[#58a6ff] mb-2 font-jetbrains">100%</div>
              <div className="text-sm font-bold text-[#c9d1d9] mb-2">AST-Grounded Claims</div>
              <div className="text-[11px] text-[#8b949e] font-jetbrains">Zero hallucinated architecture maps. Every insight is verified against the dependency graph.</div>
            </div>
            <div className="bg-[#161b22] border border-[#30363d] p-6 rounded-lg text-center">
              <div className="text-3xl font-black text-[#3fb950] mb-2 font-jetbrains">&lt; 2s</div>
              <div className="text-sm font-bold text-[#c9d1d9] mb-2">Cached Re-Analysis</div>
              <div className="text-[11px] text-[#8b949e] font-jetbrains">SHA-keyed disk cache returns previous results in milliseconds. First-run analysis takes 60–120s.</div>
            </div>
            <div className="bg-[#161b22] border border-[#30363d] p-6 rounded-lg text-center">
              <div className="text-3xl font-black text-[#a371f7] mb-2 font-jetbrains">Instant</div>
              <div className="text-sm font-bold text-[#c9d1d9] mb-2">SHA-Based Caching</div>
              <div className="text-[11px] text-[#8b949e] font-jetbrains">Results are cached securely by commit hash. Re-analyzing the same code is instantaneous.</div>
            </div>
          </div>
        </motion.div>
        
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }} className="mt-12 text-center text-xs font-jetbrains text-[#8b949e] border-t border-[#30363d] pt-8 w-full max-w-2xl">
           <p className="mb-1">First-time analysis takes 60–120s depending on repo size. Cached repos load instantly.</p>
           <p>Groundwork uses static analysis (tree-sitter) to ensure zero hallucinated claims.</p>
        </motion.div>
      </main>
    </div>
  );
}
