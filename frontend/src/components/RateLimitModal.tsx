import React, { useState, useEffect } from 'react';
import { AlertCircle, Key, ArrowRight, RefreshCw } from 'lucide-react';

interface KeyStatus {
  id: string | number;
  remaining: number;
  reset_in_seconds: number;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (token: string) => void;
}

export function RateLimitModal({ isOpen, onClose, onSubmit }: Props) {
  const [token, setToken] = useState("");
  const [keyStatuses, setKeyStatuses] = useState<KeyStatus[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    fetchKeyStatus();
    const interval = setInterval(fetchKeyStatus, 5000);
    return () => clearInterval(interval);
  }, [isOpen]);

  const fetchKeyStatus = async () => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8001'}/api/key-status`);
      if (res.ok) {
        const data = await res.json();
        setKeyStatuses(data.keys || []);
      }
    } catch {
      // silent — backend may not be running yet
    }
  };

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (token.trim()) {
      onSubmit(token.trim());
    }
  };

  const formatReset = (seconds: number) => {
    if (seconds <= 0) return "Ready";
    if (seconds < 60) return `${seconds}s`;
    return `${Math.ceil(seconds / 60)}m`;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="bg-[#161b22] border border-[#da3633]/40 rounded-xl w-full max-w-lg shadow-2xl overflow-hidden">
        
        {/* Header */}
        <div className="p-5 border-b border-[#30363d] flex items-start gap-3 bg-[#da3633]/5">
          <div className="w-9 h-9 rounded-full bg-[#da3633]/15 flex items-center justify-center flex-shrink-0 mt-0.5">
            <AlertCircle className="w-5 h-5 text-[#ff7b72]" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-[#c9d1d9]">API Rate Limit Hit</h2>
            <p className="text-sm text-[#8b949e] mt-0.5">
              All pooled tokens for this action are exhausted. Provide your own API key to continue immediately.
            </p>
          </div>
        </div>

        {/* Key pool status */}
        {keyStatuses.length > 0 && (
          <div className="px-5 pt-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-bold text-[#8b949e] uppercase tracking-wider">Pool Status</p>
              <button onClick={fetchKeyStatus} className="text-[#8b949e] hover:text-[#c9d1d9] transition-colors">
                <RefreshCw className="w-3 h-3" />
              </button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {keyStatuses.map(k => {
                const isReady = k.remaining > 10 || k.remaining === -1;
                const maxReq = 5000;
                const pct = k.remaining === -1 ? 100 : Math.max(0, Math.min(100, (k.remaining / maxReq) * 100));
                
                return (
                  <div key={k.id} className={`rounded-md p-3 border ${isReady ? 'border-[#238636]/40 bg-[#238636]/5' : 'border-[#da3633]/30 bg-[#da3633]/5'}`}>
                    <div className="flex items-center justify-between text-xs font-mono mb-2">
                      <span className="text-[#8b949e]">Key {k.id}</span>
                      <span className={isReady ? 'text-[#3fb950]' : 'text-[#ff7b72]'}>
                        {k.remaining === -1 ? 'Unknown' : isReady ? `${k.remaining} left` : `Resets in ${formatReset(k.reset_in_seconds)}`}
                      </span>
                    </div>
                    {/* Gauge bar */}
                    <div className="w-full h-1.5 bg-[#0d1117] rounded-full overflow-hidden">
                      <div 
                        className={`h-full transition-all duration-500 ${pct > 20 ? 'bg-[#3fb950]' : pct > 5 ? 'bg-[#d29922]' : 'bg-[#ff7b72]'}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* BYOK form */}
        <form onSubmit={handleSubmit} className="p-5">
          <label className="block text-sm font-bold text-[#c9d1d9] mb-2">
            Your API Key
          </label>
          <div className="relative mb-3">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Key className="w-4 h-4 text-[#8b949e]" />
            </div>
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              className="w-full bg-[#0d1117] border border-[#30363d] rounded-md py-2.5 pl-10 pr-3 text-[#c9d1d9] font-mono text-sm focus:outline-none focus:border-[#58a6ff] focus:ring-1 focus:ring-[#58a6ff]"
              placeholder="github_pat_..., gsk_..., sk-..., sk-ant-..., or AIza..."
              required
            />
          </div>

          <div className="text-xs text-[#8b949e] mb-4 bg-[#0d1117] border border-[#30363d] rounded-md p-3 space-y-1">
            <p className="font-semibold text-[#c9d1d9] mb-1.5">Which key should I provide?</p>
            <p>1. If downloading a repo failed: Provide a <strong className="text-[#c9d1d9]">GitHub PAT</strong></p>
            <p>2. If Mentor or Q&A failed: Provide a <strong className="text-[#c9d1d9]">Groq</strong>, <strong className="text-[#c9d1d9]">Gemini</strong>, <strong className="text-[#c9d1d9]">OpenAI</strong>, or <strong className="text-[#c9d1d9]">Anthropic</strong> key</p>
            <p>3. Paste the exact key above and click <strong className="text-[#c9d1d9]">Continue</strong></p>
          </div>

          <div className="flex gap-3 justify-end">
            <button type="button" onClick={onClose}
              className="px-4 py-2 bg-[#21262d] text-[#c9d1d9] border border-[#30363d] rounded-md font-semibold text-sm hover:bg-[#30363d] transition-colors">
              Cancel
            </button>
            <button type="submit"
              className="px-4 py-2 bg-[#238636] text-white border border-[#2ea043] rounded-md font-semibold text-sm flex items-center gap-2 hover:bg-[#2ea043] transition-colors">
              Continue <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
