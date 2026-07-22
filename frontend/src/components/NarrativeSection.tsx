import React, { useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  readme: string;
}

export function NarrativeSection({ readme }: Props) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Escape key closes expanded modal
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsExpanded(false); };
    if (isExpanded) window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isExpanded]);

  const content = (
    <section className={`w-full bg-[#161b22] border border-[#30363d] rounded-md p-8 md:p-10 shadow-sm overflow-y-auto relative ${isExpanded ? 'h-full border-none' : 'mt-2'}`}>
      <button 
        onClick={() => setIsExpanded(!isExpanded)} 
        className="absolute top-4 right-4 text-[#8b949e] hover:text-[#c9d1d9] flex items-center justify-center transition-colors bg-[#21262d] border border-[#30363d] rounded p-2"
        title={isExpanded ? "Minimize" : "Expand"}
      >
        {isExpanded ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-5 h-5" />}
      </button>
      <div className="max-w-4xl mx-auto">
        <ReactMarkdown 
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({node, ...props}) => <h1 className="text-4xl md:text-5xl font-black tracking-tighter text-white mb-8 border-b border-[#30363d] pb-6 font-sans" {...props} />,
            h2: ({node, ...props}) => <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-[#58a6ff] mt-12 mb-6 font-sans" {...props} />,
            h3: ({node, ...props}) => <h3 className="text-xl md:text-2xl font-semibold text-[#c9d1d9] mt-8 mb-4 font-sans" {...props} />,
            p: ({node, ...props}) => <div className="text-base md:text-lg leading-[1.8] text-[#8b949e] mb-6 font-sans font-medium" {...props} />,
            ul: ({node, ...props}) => <ul className="list-disc list-outside ml-6 space-y-3 mb-8 text-[#8b949e] font-sans text-base md:text-lg" {...props} />,
            ol: ({node, ...props}) => <ol className="list-decimal list-outside ml-6 space-y-3 mb-8 text-[#8b949e] font-sans text-base md:text-lg" {...props} />,
            li: ({node, ...props}) => <li className="pl-2" {...props} />,
            strong: ({node, ...props}) => <strong className="font-bold text-[#c9d1d9]" {...props} />,
            a: ({node, ...props}) => <a className="text-[#58a6ff] hover:underline hover:text-[#79c0ff] transition-colors" {...props} />,
            code: ({node, inline, className, children, ...props}: any) => {
              if (inline) {
                return <code className="bg-[#161b22] text-[#c9d1d9] px-1.5 py-0.5 rounded text-[0.9em] border border-[#30363d] font-mono shadow-sm" {...props}>{children}</code>;
              }
              return (
                <div className="my-6 rounded-lg overflow-hidden border border-[#30363d] shadow-md bg-[#0d1117]">
                  <div className="bg-[#161b22] px-4 py-2 border-b border-[#30363d] flex gap-2">
                    <div className="w-3 h-3 rounded-full bg-[#ff5f56]" />
                    <div className="w-3 h-3 rounded-full bg-[#ffbd2e]" />
                    <div className="w-3 h-3 rounded-full bg-[#27c93f]" />
                  </div>
                  <pre className="p-4 overflow-x-auto">
                    <code className="font-mono text-sm text-[#e6edf3]" {...props}>{children}</code>
                  </pre>
                </div>
              );
            },
          }}
        >
          {readme.replace(/##\s*Component Diagram[\s\S]*/gi, '')}
        </ReactMarkdown>
      </div>
    </section>
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
