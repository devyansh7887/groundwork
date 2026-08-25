"use client";

import React, { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Issue {
  number: number;
  title: string;
  body: string;
  author: string;
  state: string;
  labels: string[];
  comments: number;
  created_at?: string;
  html_url?: string;
  _difficulty?: "easy" | "medium" | "hard";
  _difficulty_reason?: string;
  _score?: number;
}

interface ContributionGuide {
  issue_title: string;
  issue_url: string;
  difficulty: string;
  difficulty_reason: string;
  target_files: string[];
  understanding: string;
  what_needs_to_change: string;
  diff: string;
  test_code: string;
  pr_title: string;
  pr_description: string;
  confidence: "high" | "partial" | "low";
  confidence_reason: string;
}

interface QAMessage {
  role: "user" | "ai";
  text: string;
  cited_file?: string | null;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const DIFFICULTY_CONFIG = {
  easy: { color: "text-emerald-400", bg: "bg-emerald-400/10 border-emerald-400/30", icon: "", label: "Easy" },
  medium: { color: "text-amber-400", bg: "bg-amber-400/10 border-amber-400/30", icon: "", label: "Medium" },
  hard: { color: "text-red-400", bg: "bg-red-400/10 border-red-400/30", icon: "", label: "Hard" },
};

const CONFIDENCE_CONFIG = {
  high: { color: "text-emerald-400", bg: "bg-emerald-400/10 border-emerald-400/30", icon: "", label: "High Confidence" },
  partial: { color: "text-amber-400", bg: "bg-amber-400/10 border-amber-400/30", icon: "", label: "Partial - Review Needed" },
  low: { color: "text-red-400", bg: "bg-red-400/10 border-red-400/30", icon: "", label: "Low - Human Judgment Required" },
};

const GFI_LABELS = ["good first issue", "good-first-issue", "beginner", "starter", "easy"];
const HW_LABELS = ["help wanted", "help-wanted"];
const BUG_LABELS = ["bug", "fix"];

function isGoodFirstIssue(labels: string[]) {
  return labels.some(l => GFI_LABELS.includes(l.toLowerCase()));
}
function isHelpWanted(labels: string[]) {
  return labels.some(l => HW_LABELS.includes(l.toLowerCase()));
}
function isBug(labels: string[]) {
  return labels.some(l => BUG_LABELS.includes(l.toLowerCase()));
}

function timeAgo(dateStr?: string) {
  if (!dateStr) return "";
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 2592000) return `${Math.floor(diff / 86400)}d ago`;
  return `${Math.floor(diff / 2592000)}mo ago`;
}

// ─── Subcomponents ────────────────────────────────────────────────────────────

function DiffBlock({ diff }: { diff: string }) {
  const [copied, setCopied] = useState(false);
  const lines = diff.split("\n");
  const copy = () => {
    navigator.clipboard.writeText(diff);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="relative group rounded-lg overflow-hidden border border-[#30363d] bg-[#0d1117]">
      <div className="flex items-center justify-between px-4 py-2 bg-[#161b22] border-b border-[#30363d]">
        <span className="text-xs font-jetbrains text-[#8b949e] uppercase tracking-wider">Unified Diff Patch</span>
        <button onClick={copy} className="text-xs px-2 py-1 rounded bg-[#21262d] hover:bg-[#30363d] text-[#8b949e] hover:text-[#c9d1d9] transition-colors">
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 text-xs font-jetbrains max-h-96">
        {lines.map((line, i) => {
          let cls = "text-[#c9d1d9]";
          if (line.startsWith("+") && !line.startsWith("+++")) cls = "text-emerald-400 bg-emerald-400/5";
          else if (line.startsWith("-") && !line.startsWith("---")) cls = "text-red-400 bg-red-400/5";
          else if (line.startsWith("@@")) cls = "text-[#58a6ff]";
          else if (line.startsWith("---") || line.startsWith("+++")) cls = "text-[#8b949e]";
          return <div key={i} className={`${cls} block leading-relaxed`}>{line || " "}</div>;
        })}
      </pre>
    </div>
  );
}

function CodeBlock({ code, label = "bash" }: { code: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="relative group rounded-lg overflow-hidden border border-[#30363d] bg-[#0d1117]">
      <div className="flex items-center justify-between px-4 py-2 bg-[#161b22] border-b border-[#30363d]">
        <span className="text-xs font-jetbrains text-[#8b949e] uppercase">{label}</span>
        <button onClick={copy} className="text-xs px-2 py-1 rounded bg-[#21262d] hover:bg-[#30363d] text-[#8b949e] hover:text-[#c9d1d9] transition-colors">
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 text-xs font-jetbrains text-[#c9d1d9] max-h-64">
        <code>{code}</code>
      </pre>
    </div>
  );
}

// ─── In-Wizard QA Panel ───────────────────────────────────────────────────────

function QAPanel({
  guide,
  repoUrl,
  sessionToken,
  onClose,
}: {
  guide: ContributionGuide;
  repoUrl: string;
  sessionToken: string | null;
  onClose: () => void;
}) {
  const [messages, setMessages] = useState<QAMessage[]>([
    { role: "ai", text: " Hi! I'm here to help you understand this contribution. What's confusing you?" }
  ]);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const ask = async () => {
    if (!input.trim() || asking) return;
    const q = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", text: q }]);
    setAsking(true);

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/draft/qa`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          repo_url: repoUrl,
          question: q,
          issue_title: guide.issue_title,
          understanding: guide.understanding,
          what_needs_to_change: guide.what_needs_to_change,
          target_files: guide.target_files,
        }),
      });
      const data = await res.json();
      setMessages(prev => [...prev, { role: "ai", text: data.answer || "No answer returned.", cited_file: data.cited_file }]);
    } catch {
      setMessages(prev => [...prev, { role: "ai", text: "Sorry, I couldn't reach the AI right now. Try again in a moment." }]);
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#0d1117] border-l border-[#30363d]">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#30363d] bg-[#161b22]">
        <div className="flex items-center gap-2">
          <span className="text-[#a371f7]">[?]</span>
          <span className="text-sm font-semibold text-[#c9d1d9]">Ask a Question</span>
        </div>
        <button onClick={onClose} className="text-[#8b949e] hover:text-[#c9d1d9] transition-colors">
          <span>[*]</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
              msg.role === "user"
                ? "bg-[#1f6feb] text-white"
                : "bg-[#161b22] border border-[#30363d] text-[#c9d1d9]"
            }`}>
              {msg.text}
              {msg.cited_file && (
                <div className="mt-2 text-xs font-jetbrains text-[#8b949e] border-t border-[#30363d] pt-2">
                   {msg.cited_file}
                </div>
              )}
            </div>
          </div>
        ))}
        {asking && (
          <div className="flex justify-start">
            <div className="bg-[#161b22] border border-[#30363d] rounded-xl px-4 py-3 flex items-center gap-2 text-sm text-[#8b949e]">
              <span className="animate-spin">...</span> Thinking...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="p-4 border-t border-[#30363d]">
        <form onSubmit={(e) => { e.preventDefault(); ask(); }} className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="What don't you understand?"
            className="flex-1 bg-[#161b22] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-[#c9d1d9] placeholder-[#8b949e] focus:outline-none focus:border-[#58a6ff]"
          />
          <button
            type="submit"
            disabled={!input.trim() || asking}
            className="p-2 bg-[#1f6feb] hover:bg-[#388bfd] disabled:opacity-50 text-white rounded-lg transition-colors flex items-center justify-center min-w-[36px]"
          >
            <span>[*]</span>
          </button>
        </form>
      </div>
    </div>
  );
}

// ─── Wizard Panel ─────────────────────────────────────────────────────────────

function ContributionWizardPanel({
  guide,
  repoUrl,
  sessionToken,
}: {
  guide: ContributionGuide;
  repoUrl: string;
  sessionToken: string | null;
}) {
  const [activeTab, setActiveTab] = useState<"code" | "steps">("code");
  const [showQA, setShowQA] = useState(false);
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());

  const repoPath = repoUrl.replace("https://github.com/", "").replace(/\/$/, "");
  const [, repo] = repoPath.split("/");

  const conf = CONFIDENCE_CONFIG[guide.confidence] || CONFIDENCE_CONFIG.low;
  const diff = guide.confidence;

  const GIT_STEPS = [
    {
      id: 0,
      icon: () => <span className="w-4 h-4 text-center block">Y</span>,
      title: "Fork & Clone",
      color: "text-[#3fb950]",
      content: (
        <div className="space-y-3">
          <div className="bg-[#161b22] border border-[#3fb950] p-4 rounded-lg">
            <p className="text-xs font-bold text-[#3fb950] mb-1"> What is a Fork?</p>
            <p className="text-sm text-[#8b949e] leading-relaxed">
              You can't edit the original project directly - it's not yours. A <strong className="text-[#c9d1d9]">Fork</strong> copies the project to your GitHub account.
              Once forked, you own that copy and can edit it freely.
            </p>
          </div>
          <ol className="list-decimal list-inside space-y-2 text-sm text-[#c9d1d9]">
            <li>Go to <a href={repoUrl} target="_blank" rel="noreferrer" className="text-[#58a6ff] hover:underline">{repoPath}</a> → click the <strong>Fork</strong> button (top right)</li>
            <li>Then run these commands (replace YOUR-USERNAME):</li>
          </ol>
          <CodeBlock code={`git clone https://github.com/YOUR-USERNAME/${repo}.git\ncd ${repo}`} label="terminal" />
        </div>
      )
    },
    {
      id: 1,
      icon: () => <span className="w-4 h-4 text-center block">-&gt;</span>,
      title: "Create Branch",
      color: "text-[#58a6ff]",
      content: (
        <div className="space-y-3">
          <div className="bg-[#161b22] border border-[#58a6ff] p-4 rounded-lg">
            <p className="text-xs font-bold text-[#58a6ff] mb-1"> Why branch?</p>
            <p className="text-sm text-[#8b949e] leading-relaxed">
              Think of <code className="bg-[#0d1117] px-1 rounded text-[#c9d1d9]">main</code> as a published book. You don't scribble on the original pages -
              you make a copy of relevant pages (a branch), work on them, then ask the authors to include your changes.
            </p>
          </div>
          <CodeBlock code={`git checkout -b fix/${guide.issue_title.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 40)}`} label="terminal" />
        </div>
      )
    },
    {
      id: 2,
      icon: () => <span className="w-4 h-4 text-center block">&lt;/&gt;</span>,
      title: "Make Changes",
      color: "text-[#a371f7]",
      content: (
        <div className="space-y-3">
          <div className="bg-[#161b22] border border-[#a371f7] p-4 rounded-lg">
            <p className="text-xs font-bold text-[#a371f7] mb-1"> Files to edit:</p>
            <div className="flex flex-wrap gap-2 mt-2">
              {guide.target_files.length > 0 ? guide.target_files.map(f => (
                <code key={f} className="text-xs bg-[#0d1117] px-2 py-1 rounded border border-[#30363d] text-[#c9d1d9]">{f.split("/").slice(-2).join("/")}</code>
              )) : <span className="text-xs text-[#8b949e]">Check the AI guidance above for specific files</span>}
            </div>
          </div>
          <p className="text-sm text-[#8b949e]">
            Open the file(s) above in your code editor and apply the change shown in the <strong className="text-[#c9d1d9]">Code Solution</strong> tab.
            Not sure what to change? Hit <span className="text-[#a371f7]">"I don't understand"</span> to ask.
          </p>
          <button
            onClick={() => setShowQA(true)}
            className="text-sm text-[#a371f7] hover:text-[#c084fc] flex items-center gap-1 transition-colors"
          >
            <span className="w-3.5 h-3.5">[?]</span> I don't understand something
          </button>
        </div>
      )
    },
    {
      id: 3,
      icon: () => <span className="w-4 h-4 text-center block">#</span>,
      title: "Commit & Push",
      color: "text-[#f97316]",
      content: (
        <div className="space-y-3">
          <div className="bg-[#161b22] border border-[#f97316] p-4 rounded-lg">
            <p className="text-xs font-bold text-[#f97316] mb-1"> Save vs Commit vs Push?</p>
            <p className="text-sm text-[#8b949e] leading-relaxed">
              <code className="text-[#c9d1d9]">git add</code> = tell Git which files to save.<br />
              <code className="text-[#c9d1d9]">git commit</code> = actually save a snapshot with a message.<br />
              <code className="text-[#c9d1d9]">git push</code> = upload your saved snapshot to GitHub.
            </p>
          </div>
          <CodeBlock code={`git add .\ngit commit -m "Fix: ${guide.issue_title.slice(0, 60)}"\ngit push -u origin HEAD`} label="terminal" />
        </div>
      )
    },
    {
      id: 4,
      icon: () => <span className="w-4 h-4 text-center block">PR</span>,
      title: "Open PR",
      color: "text-[#ec4899]",
      content: (
        <div className="space-y-3">
          <div className="bg-[#161b22] border border-[#ec4899] p-4 rounded-lg">
            <p className="text-xs font-bold text-[#ec4899] mb-1"> What is a Pull Request?</p>
            <p className="text-sm text-[#8b949e] leading-relaxed">
              You've fixed the bug in your Fork. Now you need to formally ask the maintainers: "Hey, please pull my changes into your project!"
              That's a <strong className="text-[#c9d1d9]">Pull Request</strong> (PR).
            </p>
          </div>
          <div className="bg-[#0d1117] border border-[#30363d] rounded-lg p-4 space-y-3">
            <div>
              <div className="text-xs text-[#8b949e] font-jetbrains mb-1">PR Title</div>
              <div className="text-sm text-[#c9d1d9] font-medium">{guide.pr_title}</div>
            </div>
            <div>
              <div className="text-xs text-[#8b949e] font-jetbrains mb-1">PR Description (copy this)</div>
              <div className="text-xs text-[#8b949e] max-h-40 overflow-y-auto font-jetbrains whitespace-pre-wrap">
                {guide.pr_description}
              </div>
            </div>
          </div>
          <a
            href={`${repoUrl}/compare`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-[#238636] hover:bg-[#2ea043] text-white text-sm font-semibold rounded-lg transition-colors"
          >
            <span>-&gt;</span> Open PR on GitHub
          </a>
        </div>
      )
    },
  ];

  const [activeStep, setActiveStep] = useState(0);

  return (
    <div className="flex h-full">
      {/* Main wizard content */}
      <div className={`flex flex-col flex-1 overflow-hidden transition-all ${showQA ? "w-1/2" : "w-full"}`}>
        {/* Confidence banner */}
        {diff !== "high" && (
          <div className={`mx-4 mt-4 p-3 rounded-lg border ${conf.bg} flex items-start gap-2`}>
            <span className="text-base leading-none">{conf.icon}</span>
            <div className="flex-1">
              <div className={`text-xs font-bold ${conf.color}`}>{conf.label}</div>
              <p className="text-xs text-[#8b949e] mt-0.5">{guide.confidence_reason}</p>
            </div>
          </div>
        )}

        {/* Tab bar: Code Solution | How to Submit */}
        <div className="flex border-b border-[#30363d] mx-4 mt-4 gap-1">
          {[
            { id: "code", label: " Code Solution", desc: "The exact code change" },
            { id: "steps", label: " How to Submit", desc: "Fork → PR step-by-step" },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as "code" | "steps")}
              className={`px-4 py-2.5 text-sm font-semibold border-b-2 transition-colors ${
                activeTab === tab.id
                  ? "border-[#58a6ff] text-[#58a6ff]"
                  : "border-transparent text-[#8b949e] hover:text-[#c9d1d9]"
              }`}
            >
              {tab.label}
            </button>
          ))}
          <div className="flex-1" />
          <button
            onClick={() => setShowQA(!showQA)}
            className={`px-3 py-2 text-sm font-semibold flex items-center gap-1.5 transition-colors ${showQA ? "text-[#a371f7]" : "text-[#8b949e] hover:text-[#a371f7]"}`}
          >
            <span>[?]</span> Ask
          </button>
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {activeTab === "code" && (
            <>
              {/* Understanding */}
              <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
                <div className="text-xs font-jetbrains text-[#58a6ff] uppercase tracking-wider mb-2">What this issue is about</div>
                <p className="text-sm text-[#c9d1d9] leading-relaxed">{guide.understanding}</p>
              </div>

              {/* What needs to change */}
              <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
                <div className="text-xs font-jetbrains text-[#a371f7] uppercase tracking-wider mb-2">Step-by-Step Instructions</div>
                <div className="text-sm text-[#c9d1d9] leading-relaxed prose prose-invert prose-p:my-2 prose-ul:my-2 prose-li:my-1 max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{guide.what_needs_to_change}</ReactMarkdown>
                </div>
              </div>

              {/* Diff */}
              {guide.diff && (
                <details className="group border border-[#30363d] rounded-lg bg-[#0d1117] overflow-hidden">
                  <summary className="px-4 py-3 text-xs font-jetbrains text-[#8b949e] uppercase tracking-wider cursor-pointer hover:bg-[#161b22] transition-colors flex items-center justify-between">
                    <span>Advanced: View Raw Diff Patch</span>
                    <span className="group-open:rotate-180 transition-transform">▼</span>
                  </summary>
                  <div className="border-t border-[#30363d]">
                    <DiffBlock diff={guide.diff} />
                  </div>
                </details>
              )}

              {/* Test code */}
              {guide.test_code && (
                <div>
                  <div className="text-xs font-jetbrains text-[#8b949e] uppercase tracking-wider mb-2">Verification Test</div>
                  <CodeBlock code={guide.test_code} label="test" />
                </div>
              )}
            </>
          )}

          {activeTab === "steps" && (
            <div className="flex gap-4">
              {/* Step sidebar */}
              <div className="w-44 flex-none">
                <div className="space-y-1">
                  {GIT_STEPS.map(step => {
                    const Icon = step.icon;
                    const done = completedSteps.has(step.id);
                    const active = activeStep === step.id;
                    return (
                      <button
                        key={step.id}
                        onClick={() => setActiveStep(step.id)}
                        className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-left transition-colors ${
                          active ? "bg-[#21262d] border border-[#30363d]" : "hover:bg-[#161b22]"
                        }`}
                      >
                        <div className={`shrink-0 ${done ? "text-[#3fb950]" : active ? step.color : "text-[#484f58]"}`}>
                          {done ? <span>[+]</span> : <Icon />}
                        </div>
                        <span className={`text-xs font-semibold ${active ? "text-[#c9d1d9]" : done ? "text-[#8b949e]" : "text-[#484f58]"}`}>
                          {step.title}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Step content */}
              <div className="flex-1">
                <div className="text-xs text-[#8b949e] font-jetbrains mb-3">
                  Step {activeStep + 1} of {GIT_STEPS.length} · {GIT_STEPS[activeStep].title}
                </div>
                {GIT_STEPS[activeStep].content}
                <div className="flex items-center gap-3 mt-6 pt-4 border-t border-[#30363d]">
                  <button
                    onClick={() => setCompletedSteps(prev => new Set(prev).add(activeStep))}
                    disabled={completedSteps.has(activeStep)}
                    className="px-4 py-2 bg-[#238636] hover:bg-[#2ea043] disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-lg transition-colors"
                  >
                    {completedSteps.has(activeStep) ? "✓ Done" : "Mark as Done"}
                  </button>
                  {activeStep < GIT_STEPS.length - 1 && (
                    <button
                      onClick={() => setActiveStep(s => s + 1)}
                      className="px-4 py-2 bg-[#21262d] hover:bg-[#30363d] text-[#c9d1d9] text-xs font-semibold rounded-lg flex items-center gap-1 transition-colors"
                    >
                      Next <span className="w-3.5 h-3.5">»</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* QA Panel */}
      {showQA && (
        <div className="w-1/2 border-l border-[#30363d] flex flex-col">
          <QAPanel guide={guide} repoUrl={repoUrl} sessionToken={sessionToken} onClose={() => setShowQA(false)} />
        </div>
      )}
    </div>
  );
}

// ─── Main ContributionDrafter ─────────────────────────────────────────────────

export function ContributionDrafter({
  repoUrl,
  sessionToken,
}: {
  repoUrl: string;
  sessionToken: string | null;
}) {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [isMaximized, setIsMaximized] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [guide, setGuide] = useState<ContributionGuide | null>(null);
  const [draftError, setDraftError] = useState("");
  const [filter, setFilter] = useState<"all" | "easy" | "gfi" | "bugs">("all");

  useEffect(() => {
    fetchIssues();
  }, [repoUrl]);

  const fetchIssues = async () => {
    setLoading(true);
    setError("");
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/issues`, {
        method: "POST",
        headers,
        body: JSON.stringify({ repo_url: repoUrl }),
      });
      if (!res.ok) throw new Error("Failed to fetch issues");
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setIssues(data.issues || []);
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectIssue = async (issue: Issue) => {
    setSelectedIssue(issue);
    setGuide(null);
    setDraftError("");
    setDrafting(true);

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/draft`, {
        method: "POST",
        headers,
        body: JSON.stringify({ repo_url: repoUrl, issue }),
      });
      if (!res.ok) throw new Error("Failed to draft contribution");
      const data = await res.json();
      setGuide(data as ContributionGuide);
    } catch (e: unknown) {
      setDraftError((e as Error).message);
    } finally {
      setDrafting(false);
    }
  };

  // Filtered issues
  const filteredIssues = issues.filter(issue => {
    if (filter === "easy") return issue._difficulty === "easy";
    if (filter === "gfi") return isGoodFirstIssue(issue.labels);
    if (filter === "bugs") return isBug(issue.labels);
    return true;
  });

  const containerCls = isMaximized
    ? "fixed inset-4 z-50 bg-[#0d1117] border border-[#30363d] rounded-xl  flex flex-col overflow-hidden"
    : "w-full h-full bg-[#0d1117] border border-[#30363d] rounded-xl flex flex-col overflow-hidden";

  const easyCount = issues.filter(i => i._difficulty === "easy").length;
  const gfiCount = issues.filter(i => isGoodFirstIssue(i.labels)).length;
  const bugCount = issues.filter(i => isBug(i.labels)).length;

  return (
    <div className={containerCls}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#30363d] bg-[#161b22] flex-none">
        <div className="flex items-center gap-2">
          <span className="text-[#58a6ff]">&gt;_</span>
          <span className="text-sm font-semibold text-[#c9d1d9]">Contribution Drafter</span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-[#238636] text-[#3fb950] border border-[#238636]/30 font-jetbrains">
            {issues.length} open issues
          </span>
        </div>
        <button onClick={() => setIsMaximized(m => !m)} className="text-[#8b949e] hover:text-[#c9d1d9] transition-colors">
          {isMaximized ? <span>[_]</span> : <span>[^]</span>}
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* ── Left: Issue Browser ──────────────────────────────────────────── */}
        <div className="w-72 flex-none border-r border-[#30363d] flex flex-col bg-[#0d1117]">
          {/* Filter bar */}
          <div className="p-3 border-b border-[#30363d] space-y-2">
            <div className="flex items-center gap-1.5 text-xs text-[#8b949e]">
              <span>[*]</span> Filter issues
            </div>
            <div className="flex flex-wrap gap-1.5">
              {[
                { id: "all", label: "All", count: issues.length },
                { id: "easy", label: " Easy", count: easyCount },
                { id: "gfi", label: " GFI", count: gfiCount },
                { id: "bugs", label: " Bugs", count: bugCount },
              ].map(f => (
                <button
                  key={f.id}
                  onClick={() => setFilter(f.id as typeof filter)}
                  className={`px-2 py-1 rounded-full text-xs font-semibold border transition-colors ${
                    filter === f.id
                      ? "bg-[#1f6feb] border-[#388bfd] text-white"
                      : "bg-transparent border-[#30363d] text-[#8b949e] hover:border-[#8b949e]"
                  }`}
                >
                  {f.label} ({f.count})
                </button>
              ))}
            </div>
          </div>

          {/* Issues list */}
          <div className="flex-1 overflow-y-auto">
            {loading && (
              <div className="p-6 text-center text-sm text-[#8b949e] flex flex-col items-center gap-2">
                <span className="w-5 h-5 animate-spin">...</span>
                Fetching open issues...
              </div>
            )}
            {error && <div className="p-4 text-xs text-red-400 bg-red-400/5 m-3 rounded-lg">{error}</div>}
            {!loading && filteredIssues.length === 0 && !error && (
              <div className="p-6 text-center text-sm text-[#8b949e]">No issues match this filter.</div>
            )}

            {filteredIssues.map(issue => {
              const diff = issue._difficulty || "medium";
              const dc = DIFFICULTY_CONFIG[diff] || DIFFICULTY_CONFIG.medium;
              const isSelected = selectedIssue?.number === issue.number;
              return (
                <button
                  key={issue.number}
                  onClick={() => handleSelectIssue(issue)}
                  className={`w-full text-left p-3 pr-4 border-b border-[#30363d] transition-colors hover:bg-[#161b22] ${
                    isSelected ? "bg-[#1f6feb] border-l-2 border-l-[#58a6ff]" : "border-l-2 border-l-transparent"
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-[#c9d1d9] line-clamp-2 leading-snug mb-1.5">
                        {issue.title}
                      </p>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full border font-semibold ${dc.bg} ${dc.color}`}>
                          {dc.icon} {dc.label}
                        </span>
                        {isGoodFirstIssue(issue.labels) && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-[#238636]/40 bg-[#238636] text-[#3fb950] font-semibold">GFI</span>
                        )}
                        {isHelpWanted(issue.labels) && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-[#58a6ff]/40 bg-[#58a6ff] text-[#58a6ff] font-semibold">Help Wanted</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1.5 text-[10px] text-[#8b949e] font-jetbrains">
                        <span>#{issue.number}</span>
                        {issue.comments > 0 && <span> {issue.comments}</span>}
                        {issue.created_at && <span>{timeAgo(issue.created_at)}</span>}
                      </div>
                    </div>
                    {isSelected && drafting && <span className="w-3 h-3 animate-spin text-[#58a6ff] mt-0.5 shrink-0">...</span>}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Right: Contribution Guide ────────────────────────────────────── */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {!selectedIssue ? (
            <div className="flex-1 flex flex-col items-center justify-center text-[#8b949e] p-8 text-center">
              <div className="w-16 h-16 rounded-full bg-[#161b22] border border-[#30363d] flex items-center justify-center mb-4">
                <span className="opacity-50">-&gt;</span>
              </div>
              <h3 className="font-space text-lg font-bold text-[#c9d1d9] mb-2">Select an Issue to Start</h3>
              <p className="text-sm max-w-sm leading-relaxed">
                Pick any issue from the left panel. Groundwork will analyze the codebase, find the relevant files,
                and generate a step-by-step contribution guide.
              </p>
              <div className="mt-4 flex items-center gap-2 text-xs text-[#3fb950]">
                <span className="w-3.5 h-3.5 shrink-0">[*]</span>
                <span>Start with a <strong> Easy</strong> issue if this is your first contribution</span>
              </div>
            </div>
          ) : (
            <div className="flex flex-col flex-1 overflow-hidden">
              {/* Issue header */}
              <div className="px-5 py-4 border-b border-[#30363d] bg-[#161b22] flex-none">
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <h2 className="font-space text-base font-bold text-[#c9d1d9] leading-snug line-clamp-2">
                      {selectedIssue.title}
                      <span className="text-[#8b949e] font-normal ml-2">#{selectedIssue.number}</span>
                    </h2>
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      {guide && (
                        <span className={`text-xs px-2 py-0.5 rounded-full border font-semibold ${DIFFICULTY_CONFIG[guide.difficulty as keyof typeof DIFFICULTY_CONFIG]?.bg} ${DIFFICULTY_CONFIG[guide.difficulty as keyof typeof DIFFICULTY_CONFIG]?.color}`}>
                          {DIFFICULTY_CONFIG[guide.difficulty as keyof typeof DIFFICULTY_CONFIG]?.icon} {guide.difficulty_reason}
                        </span>
                      )}
                      {selectedIssue.html_url && (
                        <a
                          href={selectedIssue.html_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-[#58a6ff] hover:underline flex items-center gap-0.5"
                        >
                          View on GitHub <span className="w-3 h-3">»</span>
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Content area */}
              <div className="flex-1 overflow-hidden">
                {drafting && (
                  <div className="flex flex-col items-center justify-center h-full text-[#8b949e] gap-4">
                    <span className="text-2xl animate-pulse text-[#58a6ff]">&gt;_</span>
                    <div className="text-sm text-center">
                      <p className="font-semibold text-[#c9d1d9]">Analyzing codebase...</p>
                      <p className="text-xs mt-1 font-jetbrains text-[#8b949e]">Awaiting response from Drafter Agent</p>
                    </div>
                  </div>
                )}
                {draftError && (
                  <div className="p-6 m-4 rounded-lg bg-red-400/5 border border-red-400/20 text-sm text-red-400">
                    {draftError}
                  </div>
                )}
                {guide && !drafting && (
                  <ContributionWizardPanel guide={guide} repoUrl={repoUrl} sessionToken={sessionToken} />
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
