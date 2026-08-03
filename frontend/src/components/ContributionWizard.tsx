"use client";

import React, { useState, useEffect } from "react";
import { CheckCircle2, ChevronRight, Circle, GitBranch, GitFork, Code, GitCommit, GitPullRequest, Search, Terminal, Maximize2, Minimize2 } from "lucide-react";

interface DraftPatch {
  issue_title?: string;
  target_file?: string;
  diff?: string;
  test_code?: string;
  pr_description?: string;
}

interface Props {
  repoUrl: string;
  action?: any;
  onClose?: () => void;
  onDraftRequest: (actionPayload?: any) => Promise<DraftPatch | null>;
}

type Level = "beginner" | "intermediate" | "advanced";

const STEPS = [
  { id: "find", label: "Find Issue", icon: Search },
  { id: "fork", label: "Fork & Clone", icon: GitFork },
  { id: "branch", label: "Create Branch", icon: GitBranch },
  { id: "code", label: "Make Changes", icon: Code },
  { id: "commit", label: "Commit", icon: GitCommit },
  { id: "pr", label: "Open PR", icon: GitPullRequest },
];

export function ContributionWizard({ repoUrl, action, onClose, onDraftRequest }: Props) {
  const [level, setLevel] = useState<Level>("beginner");
  const [currentStepIdx, setCurrentStepIdx] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set());
  const [isExpanded, setIsExpanded] = useState(false);
  
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<DraftPatch | null>(null);

  const repoPath = repoUrl.replace("https://github.com/", "").replace(/\/$/, "");
  const [owner, repo] = repoPath.split("/");

  // Reset state if action changes
  useEffect(() => {
    if (action) {
      setCurrentStepIdx(0);
      setDraft(null);
    }
  }, [action]);

  // Escape key closes expanded modal
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsExpanded(false); };
    if (isExpanded) window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isExpanded]);

  // Load progress from local storage
  useEffect(() => {
    const saved = localStorage.getItem(`wizard_progress_${repoPath}`);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.timestamp && Date.now() - parsed.timestamp < 24 * 60 * 60 * 1000) {
          setCompletedSteps(new Set(parsed.completed));
          setCurrentStepIdx(parsed.currentIdx ?? 0);
          setLevel(parsed.level ?? "beginner");
        } else {
          localStorage.removeItem(`wizard_progress_${repoPath}`);
        }
      } catch (e) {}
    }
  }, [repoPath]);

  // Save progress
  useEffect(() => {
    localStorage.setItem(`wizard_progress_${repoPath}`, JSON.stringify({
      completed: Array.from(completedSteps),
      currentIdx: currentStepIdx,
      level,
      timestamp: Date.now()
    }));
  }, [completedSteps, currentStepIdx, level, repoPath]);

  const markComplete = () => {
    const stepId = STEPS[currentStepIdx].id;
    setCompletedSteps(prev => new Set(prev).add(stepId));
    if (currentStepIdx < STEPS.length - 1) {
      setCurrentStepIdx(c => c + 1);
    }
  };

  const handleDraft = async () => {
    setDrafting(true);
    const result = await onDraftRequest(action);
    if (result) {
      setDraft(result);
    }
    setDrafting(false);
  };

  const CodeBlock = ({ code, language = "bash" }: { code: string; language?: string }) => (
    <div className="relative group mt-3 mb-4">
      <pre className="bg-[#0d1117] border border-[#30363d] rounded-md p-4 overflow-x-auto overflow-y-auto max-h-[500px] text-sm font-mono text-[#c9d1d9]">
        <code>{code}</code>
      </pre>
      <button 
        onClick={() => navigator.clipboard.writeText(code)}
        className="absolute top-2 right-2 p-1.5 bg-[#21262d] border border-[#30363d] rounded text-[#8b949e] opacity-0 group-hover:opacity-100 transition-opacity hover:text-[#c9d1d9]"
        title="Copy to clipboard"
      >
        <Terminal className="w-4 h-4" />
      </button>
    </div>
  );

  const renderStepContent = () => {
    const step = STEPS[currentStepIdx];
    
    if (step.id === "find") {
      return (
        <div className="space-y-4">
          <h3 className="text-xl font-bold text-[#c9d1d9]">Find an Issue to Fix</h3>
          <p className="text-[#8b949e]">
            {level === "beginner" 
              ? "Welcome to your first open-source contribution! It might feel scary, but it's just like editing a shared document. First, we need to find something to work on. Open-source projects use 'Issues' to track bugs or feature requests. I've built an AI agent that will read this repository's codebase and find the easiest open issue for you to tackle, acting like a map to guide you through."
              : "We'll scan the repo for 'good first issue' or 'help wanted' labels and rank them by lowest architectural blast-radius."}
          </p>
          
          {!draft ? (
            <button 
              onClick={handleDraft}
              disabled={drafting}
              className="mt-4 px-6 py-2.5 bg-[#238636] hover:bg-[#2ea043] border border-[rgba(240,246,252,0.1)] text-white text-sm font-semibold rounded-md flex items-center transition-colors disabled:opacity-50"
            >
              {drafting ? "AI Agent is scanning issues..." : "Find Easiest Issue & Draft Patch"}
            </button>
          ) : (
            <div className="mt-6 border border-[#30363d] bg-[#161b22] rounded-lg p-5">
              <div className="flex items-center gap-2 text-[#58a6ff] mb-2 font-mono text-sm">
                <Search className="w-4 h-4" /> Issue Selected
              </div>
              <h4 className="font-bold text-[#c9d1d9] text-lg">{draft.issue_title}</h4>
              <p className="text-[#8b949e] mt-2 text-sm">Target file: <span className="font-mono bg-[#0d1117] px-1.5 py-0.5 rounded border border-[#30363d]">{draft.target_file}</span></p>
            </div>
          )}
        </div>
      );
    }

    if (step.id === "fork") {
      return (
        <div className="space-y-4">
          <h3 className="text-xl font-bold text-[#c9d1d9]">Fork and Clone</h3>
          <div className="bg-[#1f2428] border-l-4 border-[#3fb950] p-4 rounded-r-md my-4 shadow-sm">
            <h4 className="font-semibold text-[#c9d1d9] mb-1">👨‍🏫 Teacher's Note: What is a Fork?</h4>
            <p className="text-sm text-[#8b949e] leading-relaxed">
              You can't edit the original project's code directly because it belongs to them. A <strong>Fork</strong> is essentially a complete copy of their project that gets moved to your personal GitHub account. Once it's in your account, you own it! <strong>Cloning</strong> simply downloads that copy from your GitHub account to your local computer so you can edit it.
            </p>
          </div>
          <ol className="list-decimal list-inside space-y-3 text-[#c9d1d9] mt-4">
            <li>Go to <a href={repoUrl} target="_blank" rel="noreferrer" className="text-[#58a6ff] hover:underline font-semibold">{repoPath}</a> and click the <strong>Fork</strong> button in the top right.</li>
            <li>Once the fork is created, open your terminal (command prompt) and run this command to download it to your computer (replace YOUR-USERNAME with your actual GitHub username):</li>
          </ol>
          <CodeBlock code={`git clone https://github.com/YOUR-USERNAME/${repo}.git\ncd ${repo}`} />
        </div>
      );
    }

    if (step.id === "branch") {
      return (
        <div className="space-y-4">
          <h3 className="text-xl font-bold text-[#c9d1d9]">Create a Branch</h3>
          <div className="bg-[#1f2428] border-l-4 border-[#58a6ff] p-4 rounded-r-md my-4 shadow-sm">
            <h4 className="font-semibold text-[#c9d1d9] mb-1">👨‍🏫 Teacher's Note: Why Branch?</h4>
            <p className="text-sm text-[#8b949e] leading-relaxed">
              Think of the 'main' branch as the final, published book. If you're going to write a new chapter or fix a typo, you don't scribble directly on the final book! You make a copy of the pages (a new branch), do your work there, and later ask the authors to insert your pages. This command creates a new branch safely isolated from the main code.
            </p>
          </div>
          <CodeBlock code={`git checkout -b fix/${draft?.issue_title?.toLowerCase().replace(/[^a-z0-9]+/g, '-') || 'issue'}`} />
        </div>
      );
    }

    if (step.id === "code") {
      return (
        <div className="space-y-4">
          <h3 className="text-xl font-bold text-[#c9d1d9]">Make Changes</h3>
          <p className="text-[#8b949e]">
            Open <code className="bg-[#0d1117] px-1.5 py-0.5 rounded border border-[#30363d] font-mono text-sm">{draft?.target_file || 'the target file'}</code> in your editor and apply this fix.
          </p>
          
          {draft?.diff && (
            <div className="mt-4">
              <div className="text-xs font-mono text-[#8b949e] mb-2 uppercase tracking-wider">AI Drafted Patch</div>
              <CodeBlock code={draft.diff} language="diff" />
            </div>
          )}
          
          {draft?.test_code && (
            <div className="mt-4">
              <div className="text-xs font-mono text-[#8b949e] mb-2 uppercase tracking-wider">Don't forget the test</div>
              <CodeBlock code={draft.test_code} language="python" />
            </div>
          )}
        </div>
      );
    }

    if (step.id === "commit") {
      return (
        <div className="space-y-4">
          <h3 className="text-xl font-bold text-[#c9d1d9]">Commit and Push</h3>
          <div className="bg-[#1f2428] border-l-4 border-[#bc8cff] p-4 rounded-r-md my-4 shadow-sm">
            <h4 className="font-semibold text-[#c9d1d9] mb-1">👨‍🏫 Teacher's Note: Saving Your Work</h4>
            <p className="text-sm text-[#8b949e] leading-relaxed">
              Just clicking 'save' in your editor isn't enough for Git. <br/><br/>
              <code>git add .</code> tells Git "Hey, I want to include all the files I just edited in my next save."<br/>
              <code>git commit</code> actually saves the changes into a package with a descriptive message.<br/>
              <code>git push</code> uploads that saved package from your local computer back to your Fork on GitHub!
            </p>
          </div>
          <CodeBlock code={`git add .\ngit commit -m "Fix: ${draft?.issue_title || 'resolved issue'}"\ngit push -u origin HEAD`} />
        </div>
      );
    }

    if (step.id === "pr") {
      return (
        <div className="space-y-4">
          <h3 className="text-xl font-bold text-[#c9d1d9]">Open a Pull Request (PR)</h3>
          <div className="bg-[#1f2428] border-l-4 border-[#ff7b72] p-4 rounded-r-md my-4 shadow-sm">
            <h4 className="font-semibold text-[#c9d1d9] mb-1">👨‍🏫 Teacher's Note: The Final Step</h4>
            <p className="text-sm text-[#8b949e] leading-relaxed">
              You've fixed the bug in your Fork. But the original project doesn't know about it yet! A <strong>Pull Request</strong> is literally you formally requesting the maintainers to "Pull" your changes from your branch into their main project. Be polite, explain exactly what you fixed, and provide tests if you can. We drafted a good PR description for you below.
            </p>
          </div>
          
          <div className="mt-4 border border-[#30363d] rounded bg-[#0d1117] p-4">
            <div className="text-xs font-mono text-[#8b949e] mb-2">PR Title</div>
            <div className="font-semibold text-[#c9d1d9] mb-4">Fix: {draft?.issue_title || 'Resolve issue'}</div>
            
            <div className="text-xs font-mono text-[#8b949e] mb-2">PR Body</div>
            <pre className="text-[#c9d1d9] whitespace-pre-wrap font-sans text-sm">{draft?.pr_description || 'Describes the fix applied.'}</pre>
          </div>
          
          <div className="mt-6 flex justify-center">
            <a 
              href={`${repoUrl}/compare`} 
              target="_blank" 
              rel="noreferrer"
              className="px-6 py-2.5 bg-[#238636] hover:bg-[#2ea043] text-white font-semibold rounded flex items-center gap-2"
            >
              <GitPullRequest className="w-5 h-5" /> Open PR on GitHub
            </a>
          </div>
        </div>
      );
    }

    return null;
  };

  return (
    <>
      {isExpanded && (
        <div
          className="fixed inset-0 z-[90] bg-black/60 backdrop-blur-sm"
          onClick={() => setIsExpanded(false)}
        />
      )}
      <div
        className={`${
          isExpanded
            ? 'fixed inset-0 z-[100] flex items-center justify-center p-4 md:p-10'
            : 'w-full'
        }`}
      >
        <div
          className={`w-full bg-[#0d1117] border border-[#30363d] rounded-xl flex flex-col md:flex-row overflow-hidden shadow-sm ${
            isExpanded ? 'max-w-[85vw] max-h-[85vh] shadow-2xl' : ''
          }`}
          style={{ minHeight: isExpanded ? '75vh' : 600 }}
          onClick={e => e.stopPropagation()}
        >
          {/* Sidebar - Progress Map */}
          <div className={`${isExpanded ? 'w-full md:w-80' : 'w-full md:w-64'} bg-[#161b22] border-r border-[#30363d] p-6 flex flex-col flex-shrink-0`}>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold text-[#c9d1d9] tracking-tight flex items-center gap-2">
                <Code className="w-5 h-5 text-[#58a6ff]" />
                Wizard
              </h2>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setIsExpanded(!isExpanded)}
                  className="text-[#8b949e] hover:text-[#c9d1d9] flex items-center justify-center transition-colors"
                  title={isExpanded ? "Minimize (Esc)" : "Expand"}
                >
                  {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>
                {onClose && (
                  <button onClick={onClose} className="text-[#8b949e] hover:text-[#c9d1d9] text-xs underline">
                    Close
                  </button>
                )}
              </div>
            </div>

            {action && (
              <div className="mb-6 p-3 bg-[#0d1117] border border-[#30363d] rounded text-xs text-[#8b949e]">
                <span className="font-bold text-[#58a6ff] block mb-1">Target Action:</span>
                <span className="text-[#c9d1d9] font-medium">{action.title}</span><br/>
                <span className="font-mono mt-1 block">{action.target_file?.split("/").pop()}</span>
              </div>
            )}

            <div className="mb-8">
              <label className="text-xs font-bold text-[#8b949e] uppercase tracking-wider mb-2 block">Your Level</label>
              <select
                value={level}
                onChange={e => setLevel(e.target.value as Level)}
                className="w-full bg-[#0d1117] border border-[#30363d] text-[#c9d1d9] text-sm rounded px-3 py-2 outline-none focus:border-[#58a6ff]"
              >
                <option value="beginner">🌱 Complete Beginner</option>
                <option value="intermediate">🌿 Know Some Code</option>
                <option value="advanced">🌳 Developer</option>
              </select>
            </div>

            <div className="flex-1 overflow-y-auto">
              {STEPS.map((step, idx) => {
                const Icon = step.icon;
                const isCompleted = completedSteps.has(step.id);
                const isCurrent = currentStepIdx === idx;
                return (
                  <button
                    key={step.id}
                    onClick={() => setCurrentStepIdx(idx)}
                    className={`w-full flex items-center gap-3 py-3 px-2 text-left transition-colors relative ${
                      isCurrent ? "bg-[#0d1117] rounded-md" : "hover:bg-[#0d1117]/50 rounded-md"
                    }`}
                  >
                    {isCurrent && <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-[#58a6ff] rounded-r" />}
                    <div className={`shrink-0 ${isCompleted ? "text-[#3fb950]" : isCurrent ? "text-[#58a6ff]" : "text-[#484f58]"}`}>
                      {isCompleted ? <CheckCircle2 className="w-5 h-5" /> : <Icon className="w-5 h-5" />}
                    </div>
                    <span className={`text-sm font-semibold ${isCurrent ? "text-[#c9d1d9]" : isCompleted ? "text-[#8b949e]" : "text-[#484f58]"}`}>
                      {step.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Main Content Area */}
          <div className="flex-1 flex flex-col p-8 bg-[#0d1117] overflow-y-auto">
            <div className="flex-1 max-w-2xl">
              <div className="flex items-center gap-2 text-[#8b949e] font-mono text-xs mb-6 uppercase tracking-wider">
                Step {currentStepIdx + 1} of {STEPS.length} <ChevronRight className="w-3 h-3" /> {STEPS[currentStepIdx].id}
              </div>
              {renderStepContent()}
            </div>
            {/* Footer */}
            <div className="mt-12 pt-6 border-t border-[#30363d] flex justify-end">
              {(!draft && STEPS[currentStepIdx].id === "find") ? null : (
                <button
                  onClick={markComplete}
                  disabled={completedSteps.has(STEPS[currentStepIdx].id)}
                  className="px-6 py-2.5 bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] text-[#c9d1d9] text-sm font-semibold rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {completedSteps.has(STEPS[currentStepIdx].id) ? "Completed" : "Mark as Complete"}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

