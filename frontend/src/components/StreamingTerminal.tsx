import React, { useEffect, useRef, useState } from 'react';

interface StreamingTerminalProps {
  logs: string[];
}

const IDLE_MESSAGES = [
  "⏳  AI is deep in thought...",
  "🔎  Cross-referencing dependencies...",
  "🧩  Connecting the dots in the codebase...",
  "📖  Reading through the source files...",
  "🤔  Making sense of the architecture...",
  "⚙️   Checking how the pieces fit together...",
  "🧠  Running language model inference...",
  "🔬  Verifying claims against the code...",
];

function humanize(log: string): string {
  // Map raw backend messages to something nicer
  const map: [RegExp, string][] = [
    [/Calling Synthesizer/i, "🧠  AI is studying the architecture..."],
    [/AFC is enabled/i, ""],  // suppress completely
    [/Retrying google/i, "⏳  Waiting for AI service, retrying..."],
    [/Verifier found issues/i, "⚠️   Some claims need correction — re-running AI..."],
    [/Proceeding to Diagram/i, "🎨  Moving on to diagram generation..."],
    [/Rate limit hit/i, "🔄  GitHub rate limit hit — switching to backup key..."],
  ];

  for (const [pattern, replacement] of map) {
    if (pattern.test(log)) return replacement;
  }
  return log;
}

export function StreamingTerminal({ logs }: StreamingTerminalProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [idleIdx, setIdleIdx] = useState(0);

  // Auto-scroll on new logs
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Cycle idle messages every 4s so the terminal always looks alive
  useEffect(() => {
    const interval = setInterval(() => {
      setIdleIdx(i => (i + 1) % IDLE_MESSAGES.length);
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  // Deduplicate progressive logs (e.g., "Downloading file... (X/Y)")
  const collapsedLogs: { text: string; isProgressing: boolean }[] = [];
  
  const progressPatterns = [
    /^(Downloading file).*/i,
    /^(Parsing AST for).*/i,
    /^(Analyzing node).*/i,
    /^(Fetching issue).*/i,
    /^(📥\s*Fetching file).*/i,
    /^(🗺️\s*\[CARTOGRAPHER\] Parsing AST).*/i
  ];

  logs.map(humanize).filter(l => l !== "").forEach((log) => {
    let matched = false;
    for (const pattern of progressPatterns) {
      const match = log.match(pattern);
      if (match) {
        const prefix = match[1];
        // Check if the last log has the same prefix
        if (collapsedLogs.length > 0 && collapsedLogs[collapsedLogs.length - 1].text.startsWith(prefix)) {
          collapsedLogs[collapsedLogs.length - 1] = { text: log, isProgressing: true };
          matched = true;
          break;
        }
      }
    }
    if (!matched) {
      // If the last log was progressing, it's now finished
      if (collapsedLogs.length > 0) {
        collapsedLogs[collapsedLogs.length - 1].isProgressing = false;
      }
      collapsedLogs.push({ text: log, isProgressing: false });
    }
  });

  return (
    <div className="flex items-center justify-center min-h-[70vh] w-full p-4">
      <div className="w-full max-w-3xl bg-[#0d1117] rounded-xl border border-[#30363d] shadow-2xl overflow-hidden flex flex-col" style={{ height: 420 }}>
        {/* Terminal chrome */}
        <div className="flex items-center px-4 py-2.5 bg-[#161b22] border-b border-[#30363d] flex-shrink-0">
          <div className="flex space-x-1.5">
            <div className="w-3 h-3 rounded-full bg-[#ff5f56]" />
            <div className="w-3 h-3 rounded-full bg-[#ffbd2e]" />
            <div className="w-3 h-3 rounded-full bg-[#27c93f]" />
          </div>
          <span className="mx-auto text-xs font-mono text-[#8b949e] font-semibold tracking-widest pr-14">
            GROUNDWORK — analysis running
          </span>
        </div>

        {/* Terminal body */}
        <div className="flex-1 p-5 overflow-y-auto font-mono text-sm leading-relaxed">
          {/* Static opening line */}
          <div className="text-[#58a6ff] mb-3 flex gap-3">
            <span className="text-[#30363d] select-none">$</span>
            <span>groundwork analyze <span className="text-[#c9d1d9]">--mode=deep</span></span>
          </div>

          {collapsedLogs.length === 0 && (
            <div className="text-[#8b949e] flex gap-3 mb-1">
              <span className="text-[#30363d] select-none">›</span>
              <span>Initializing agents...</span>
            </div>
          )}

          {collapsedLogs.map((item, i) => {
            const { text: log, isProgressing } = item;
            let colorClass = "text-[#8b949e]";
            if (/✅|🎉|⚡|💾/.test(log)) colorClass = "text-[#3fb950]";
            else if (/🔍|📡|🌿|📁|🗺️|🧠|🎨|📝|📦|🔬/.test(log)) colorClass = "text-[#58a6ff]";
            else if (/⚠️|🔄|⏳|🔁/.test(log)) colorClass = "text-[#d29922]";
            else if (/🚀|🆕|🔎/.test(log)) colorClass = "text-[#bc8cff]";

            return (
              <div key={i} className={`${colorClass} mb-1.5 flex gap-3`}>
                <span className="text-[#30363d] select-none flex-shrink-0">›</span>
                <span className="whitespace-pre-wrap">{log}</span>
                {isProgressing && i === collapsedLogs.length - 1 && (
                  <span className="inline-block w-3 h-3 border-2 border-[#58a6ff] border-t-transparent rounded-full animate-spin ml-2 align-middle mt-1" />
                )}
              </div>
            );
          })}

          {/* Idle ticker — shows when no new logs coming */}
          <div className="text-[#484f58] flex gap-3 mt-1 animate-pulse">
            <span className="text-[#30363d] select-none">›</span>
            <span>{IDLE_MESSAGES[idleIdx]}</span>
          </div>

          {/* Blinking cursor */}
          <div className="flex gap-3 mt-2">
            <span className="text-[#30363d] select-none">$</span>
            <span className="w-2 h-4 bg-[#c9d1d9] animate-[pulse_1s_step-end_infinite] inline-block align-middle" />
          </div>

          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}
