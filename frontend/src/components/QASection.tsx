import React, { useState } from "react";
import ReactMarkdown from "react-markdown";

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
      {text}
    </span>
  );
};

interface Props {
  qaHistory: Array<{ q: string; a: string; claims?: Array<{ claim: string; status: string; cited_file: string }> }>;
  asking: boolean;
  qaError: string;
  question: string;
  setQuestion: (q: string) => void;
  setQaError: (err: string) => void;
  handleAsk: (e: React.FormEvent) => void;
}

export function QASection({ qaHistory, asking, qaError, question, setQuestion, setQaError, handleAsk }: Props) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Escape key closes expanded modal
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsExpanded(false); };
    if (isExpanded) window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isExpanded]);

  const content = (
    <div className={`flex-1 w-full flex flex-col bg-[#161b22] border border-[#30363d] rounded-md overflow-hidden  ${isExpanded ? 'h-full border-none' : 'h-[700px] mt-2'}`}>
      <div className="p-5 border-b border-[#30363d] bg-[#161b22] flex items-center justify-between">
        <div>
          <h3 className="font-space text-lg font-bold text-[#c9d1d9] flex items-center"><span className="w-4 h-4 mr-2 text-[#8b949e]">&gt;_</span> Grounded Q&A</h3>
          <p className="text-xs font-jetbrains text-[#8b949e] mt-1">Every claim verified via AST graph.</p>
        </div>
        <button 
          onClick={() => setIsExpanded(!isExpanded)} 
          className="text-[#8b949e] hover:text-[#c9d1d9] flex items-center justify-center transition-colors bg-[#21262d] border border-[#30363d] rounded p-1"
          title={isExpanded ? "Minimize" : "Expand"}
        >
          {isExpanded ? <span className="w-4 h-4">[_]</span> : <span className="w-4 h-4">[^]</span>}
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto p-5 space-y-6 bg-[#0d1117]">
        {qaHistory.length === 0 ? (
          <div className="text-sm font-jetbrains text-[#8b949e] text-center mt-32 px-4">
            <span className="w-10 h-10 text-[#30363d] mx-auto mb-4">&gt;_</span>
            &gt;_ Ask a question about the architecture.<br/>Responses are fact-checked concurrently.
          </div>
        ) : (
          qaHistory.map((qa, i) => (
            <div key={i} className="space-y-4">
              <div className="bg-[#161b22] border border-[#30363d] p-4 rounded-md self-end ml-8">
                <p className="text-sm md:text-base text-[#c9d1d9] font-medium">{qa.q}</p>
              </div>
              <div className="bg-[#161b22] border border-[#30363d] border border-l-[#58a6ff] p-5 rounded-md mr-4">
                {qa.claims && qa.claims.length > 0 && (
                   <div className="mb-4">
                      <Badge status={qa.claims.some(c => c.status === "Unverified") ? "Unverified" : qa.claims.some(c => c.status === "Inferred") ? "Inferred" : "Verified"} />
                   </div>
                )}
                <div className="prose prose-invert max-w-none text-base text-[#c9d1d9] leading-relaxed prose-code:text-[#c9d1d9] prose-code:bg-[#0d1117] prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:border prose-code:border-[#30363d]">
                  <ReactMarkdown
                     components={{
                       code({inline, className, children, ...props}: React.HTMLAttributes<HTMLElement> & {inline?: boolean}) {
                          const text = String(children);
                          if (inline && text.startsWith('CITATION:')) {
                            return <CitationChip text={text.replace('CITATION:', '')} />;
                          }
                          return <code className={className} {...props}>{children}</code>;
                       }
                     }}
                  >
                    {qa.a.replace(/\[([\w\.\/\-]+(?::\d+)?)\]/g, '`CITATION:$1`')}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          ))
        )}
        {asking && (
          <div className="flex justify-center py-4">
            <span className="w-5 h-5 animate-spin text-[#8b949e]">...</span>
          </div>
        )}
      </div>
      
      <div className="p-5 border-t border-[#30363d] bg-[#161b22]">
        {qaError && (
          <div className="mb-3 bg-[#da3633] border border-[#da3633]/40 text-[#ff7b72] text-xs font-jetbrains p-3 rounded flex justify-between items-center">
            <span>{qaError}</span>
            <button onClick={() => setQaError("")}><span className="w-3.5 h-3.5">[x]</span></button>
          </div>
        )}
        <form onSubmit={handleAsk} className="relative">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question..."
            className="w-full pl-4 pr-12 py-4 bg-[#0d1117] border border-[#30363d] rounded-md focus:ring-1 focus:ring-[#58a6ff] focus:border-[#58a6ff] text-base text-[#c9d1d9] placeholder-[#8b949e] font-jetbrains outline-none transition-shadow"
          />
          <button type="submit" className="absolute inset-y-0 right-2 flex items-center justify-center text-[#8b949e] hover:text-[#c9d1d9] transition-colors">
            <div className="bg-[#161b22] p-2 rounded border border-[#30363d]">
              <span className="w-5 h-5">[?]</span>
            </div>
          </button>
        </form>
      </div>
    </div>
  );

  if (isExpanded) {
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
