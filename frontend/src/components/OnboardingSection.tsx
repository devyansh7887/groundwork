import React from "react";
import { motion, AnimatePresence } from "framer-motion";

interface Props {
  role: string;
  setRole: (role: string) => void;
  level: string;
  setLevel: (level: string) => void;
  pathLoading: boolean;
  pathError: string;
  setPathError: (err: string) => void;
  path: { path: Array<{ file_path: string; rationale: string; concepts: string[] }> } | null;
  handleGeneratePath: () => void;
}

export function OnboardingSection({ role, setRole, level, setLevel, pathLoading, pathError, setPathError, path, handleGeneratePath }: Props) {
  return (
    <section className="bg-[#161b22] border border-[#30363d] rounded-md p-6">
      <h3 className="font-space text-lg font-bold text-[#c9d1d9] mb-1">Personalized Onboarding</h3>
      <p className="text-xs font-jetbrains text-[#8b949e] mb-6">Generate reading paths mapped to expertise.</p>
      
      <div className="flex gap-3 mb-5">
        <select value={role} onChange={(e) => setRole(e.target.value)} className="block w-full text-sm font-jetbrains bg-[#0d1117] border border-[#30363d] text-[#c9d1d9] rounded-md focus:ring-1 focus:ring-[#58a6ff] py-2 px-3 outline-none">
          <option value="frontend">Frontend</option>
          <option value="backend">Backend</option>
          <option value="full-stack">Full-stack</option>
        </select>
        <select value={level} onChange={(e) => setLevel(e.target.value)} className="block w-full text-sm font-jetbrains bg-[#0d1117] border border-[#30363d] text-[#c9d1d9] rounded-md focus:ring-1 focus:ring-[#58a6ff] py-2 px-3 outline-none">
          <option value="beginner">Beginner</option>
          <option value="intermediate">Intermediate</option>
          <option value="senior">Senior</option>
        </select>
      </div>
      
      <button 
        onClick={handleGeneratePath}
        disabled={pathLoading}
        className="w-full px-4 py-2.5 border border-[#30363d] text-sm font-bold font-ibm rounded-md text-[#c9d1d9] bg-[#21262d] hover:bg-[#30363d] hover:border-[#8b949e] transition-colors mb-6 flex justify-center items-center"
      >
        {pathLoading && <span className="mr-2 animate-pulse text-[#58a6ff]">&gt;_</span>}
        Generate Reading Path
      </button>
      
      <AnimatePresence>
        {pathError && (
           <div className="mb-4 bg-[#da3633] border border-[#da3633]/40 text-[#ff7b72] text-xs font-jetbrains p-3 rounded flex justify-between items-center">
             <span>{pathError}</span>
             <button onClick={() => setPathError("")}><span className="w-3.5 h-3.5">[x]</span></button>
           </div>
        )}
        {path && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
            {path.path.map((step, i) => (
              <div key={i} className="flex relative">
                <div className="flex-shrink-0 w-8 flex flex-col items-center">
                  <div className="w-8 h-8 rounded-full bg-[#161b22] border-2 border-[#30363d] text-[#c9d1d9] text-xs flex items-center justify-center font-jetbrains font-bold z-10">{i + 1}</div>
                  {i !== path.path.length - 1 && <div className="h-full w-[2px] bg-[#30363d] mt-1"></div>}
                </div>
                <div className="ml-4 pb-4 w-full">
                  <code className="text-[11px] font-jetbrains font-bold text-[#58a6ff] block mb-2 bg-[#0d1117] px-2 py-1 rounded w-max border border-[#30363d]">{step.file_path}</code>
                  <p className="text-sm text-[#c9d1d9] mb-3 leading-relaxed">{step.rationale}</p>
                  <div className="flex flex-wrap gap-2">
                    {step.concepts.map((c, j) => (
                      <span key={j} className="bg-[#0d1117] text-[#8b949e] text-[10px] font-jetbrains px-2 py-1 rounded border border-[#30363d]">{c}</span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
