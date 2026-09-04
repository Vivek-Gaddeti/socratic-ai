'use client';
import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/lib/api';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  agent_used?: string;
  score?: number;
  hint_level?: number;
  timestamp: string;
}

interface Source { page: number | string; score: number; }

function ScoreBadge({ score }: { score: number }) {
  if (score < 0) return null;
  const cls = score >= 85 ? 'score-perfect' : score >= 60 ? 'score-high' : score >= 35 ? 'score-medium' : 'score-low';
  const emoji = score >= 85 ? '🏆' : score >= 60 ? '✓' : score >= 35 ? '→' : '✗';
  return <span className={`score-badge ${cls} mt-1`}>{emoji} {Math.round(score)}%</span>;
}

function AgentBadge({ agent }: { agent?: string }) {
  if (!agent) return null;
  if (agent.startsWith('hint')) {
    const level = agent.split('_').pop();
    return <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(245,158,11,0.15)', color: '#f59e0b' }}>
      💡 Hint Level {level}
    </span>;
  }
  return <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(124,58,237,0.15)', color: 'var(--accent-purple-light)' }}>
    🦉 Socrates
  </span>;
}

function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 message-bubble">
      <div className="w-8 h-8 rounded-full flex items-center justify-center text-sm flex-shrink-0"
        style={{ background: 'linear-gradient(135deg, var(--accent-purple), var(--accent-blue))' }}>🦉</div>
      <div className="glass-card px-5 py-4" style={{ borderRadius: '4px 16px 16px 16px' }}>
        <div className="flex items-center gap-1.5">
          <span className="typing-dot" />
          <span className="typing-dot" />
          <span className="typing-dot" />
        </div>
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const { token, user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [currentConcept, setCurrentConcept] = useState('');
  const [lastScore, setLastScore] = useState(-1);
  const [showSources, setShowSources] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!authLoading && !user) router.push('/login');
  }, [user, authLoading, router]);

  useEffect(() => {
    if (token && sessionId) loadMessages();
  }, [token, sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  const loadMessages = async () => {
    try {
      const msgs = await api.getSessionMessages(sessionId, token!);
      setMessages(msgs);
      if (msgs.length === 0) {
        // Send a greeting trigger
        await sendGreeting();
      }
    } catch { router.push('/dashboard'); }
  };

  const sendGreeting = async () => {
    setSending(true);
    try {
      const res = await api.sendMessage(sessionId, "Hello! I'm ready to learn. What should we explore?", token!);
      setMessages([
        { id: 'u0', role: 'user', content: "Hello! I'm ready to learn. What should we explore?", timestamp: new Date().toISOString() },
        { id: 'a0', role: 'assistant', content: res.response, agent_used: res.agent_used, score: res.evaluation_score, timestamp: new Date().toISOString() },
      ]);
      setCurrentConcept(res.current_concept || '');
    } catch {} finally { setSending(false); }
  };

  const sendMessage = async () => {
    if (!input.trim() || sending) return;
    const userMsg = input.trim();
    setInput('');
    setSending(true);
    setMessages(prev => [...prev, {
      id: `u-${Date.now()}`, role: 'user', content: userMsg, timestamp: new Date().toISOString()
    }]);

    try {
      const res = await api.sendMessage(sessionId, userMsg, token!);
      setMessages(prev => [...prev, {
        id: `a-${Date.now()}`, role: 'assistant', content: res.response,
        agent_used: res.agent_used, score: res.evaluation_score, timestamp: new Date().toISOString()
      }]);
      setSources(res.sources || []);
      setCurrentConcept(res.current_concept || '');
      setLastScore(res.evaluation_score);
    } catch (err) {
      setMessages(prev => [...prev, {
        id: `err-${Date.now()}`, role: 'assistant',
        content: '⚠️ Something went wrong. Please try again.', timestamp: new Date().toISOString()
      }]);
    } finally { setSending(false); }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const formatContent = (text: string) => {
    // Bold **text**, convert newlines
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br/>');
  };

  if (authLoading || !user) return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg-primary)' }}>
      <div className="text-4xl animate-float">🦉</div>
    </div>
  );

  return (
    <div className="h-screen flex flex-col" style={{ background: 'var(--bg-primary)' }}>
      {/* Top bar */}
      <header className="flex items-center justify-between px-6 py-4 flex-shrink-0"
        style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)' }}>
        <div className="flex items-center gap-4">
          <button onClick={() => router.push('/dashboard')} className="btn-secondary text-sm px-3 py-1.5">← Back</button>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center text-lg"
              style={{ background: 'linear-gradient(135deg, var(--accent-purple), var(--accent-blue))' }}>🦉</div>
            <div>
              <p className="font-semibold text-sm">SocraticAI</p>
              {currentConcept && <p className="text-xs" style={{ color: 'var(--accent-purple-light)' }}>Topic: {currentConcept}</p>}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {lastScore >= 0 && (
            <div className="flex items-center gap-2 text-sm">
              <span style={{ color: 'var(--text-secondary)' }}>Last score:</span>
              <ScoreBadge score={lastScore} />
            </div>
          )}
          {sources.length > 0 && (
            <button onClick={() => setShowSources(s => !s)} className="btn-secondary text-xs px-3 py-1.5">
              📖 {showSources ? 'Hide' : 'Show'} Sources ({sources.length})
            </button>
          )}
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Chat area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
            {messages.length === 0 && !sending && (
              <div className="text-center py-20">
                <div className="text-6xl mb-4 animate-float">🦉</div>
                <p className="font-semibold text-lg mb-2">SocraticAI is thinking...</p>
                <p style={{ color: 'var(--text-secondary)' }}>Preparing your first question</p>
              </div>
            )}

            {messages.map((msg) => (
              <div key={msg.id} className={`flex items-start gap-3 message-bubble ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                {/* Avatar */}
                <div className="w-8 h-8 rounded-full flex items-center justify-center text-sm flex-shrink-0"
                  style={{
                    background: msg.role === 'user'
                      ? 'linear-gradient(135deg, var(--accent-blue), var(--accent-cyan))'
                      : 'linear-gradient(135deg, var(--accent-purple), var(--accent-blue))',
                  }}>
                  {msg.role === 'user' ? (user.name[0]?.toUpperCase() || '?') : '🦉'}
                </div>

                {/* Bubble */}
                <div className={`max-w-[75%] ${msg.role === 'user' ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
                  {msg.role === 'assistant' && <AgentBadge agent={msg.agent_used} />}
                  <div className="px-5 py-3.5 text-sm leading-relaxed"
                    style={{
                      background: msg.role === 'user' ? 'linear-gradient(135deg, rgba(59,130,246,0.25), rgba(6,182,212,0.25))' : 'var(--bg-card)',
                      border: `1px solid ${msg.role === 'user' ? 'rgba(59,130,246,0.3)' : 'var(--border)'}`,
                      borderRadius: msg.role === 'user' ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
                    }}
                    dangerouslySetInnerHTML={{ __html: formatContent(msg.content) }}
                  />
                  {msg.role === 'assistant' && msg.score !== undefined && msg.score >= 0 && (
                    <ScoreBadge score={msg.score} />
                  )}
                </div>
              </div>
            ))}

            {sending && <TypingIndicator />}
            <div ref={bottomRef} />
          </div>

          {/* Input area */}
          <div className="px-6 py-4 flex-shrink-0" style={{ background: 'var(--bg-secondary)', borderTop: '1px solid var(--border)' }}>
            <div className="flex gap-3 items-end">
              <textarea
                ref={inputRef}
                id="chat-input"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Share your thoughts... (Enter to send, Shift+Enter for new line)"
                rows={1}
                disabled={sending}
                className="input-field flex-1 resize-none"
                style={{ minHeight: '48px', maxHeight: '120px' }}
                onInput={e => {
                  const t = e.currentTarget;
                  t.style.height = 'auto';
                  t.style.height = Math.min(t.scrollHeight, 120) + 'px';
                }}
              />
              <button onClick={sendMessage} disabled={sending || !input.trim()}
                id="chat-send"
                className="btn-primary px-5 py-3 flex-shrink-0 disabled:opacity-40">
                {sending ? (
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin block" />
                ) : '→'}
              </button>
            </div>
            <p className="text-xs mt-2 text-center" style={{ color: 'var(--text-muted)' }}>
              SocraticAI will never just give you the answer — it will guide you to discover it 🦉
            </p>
          </div>
        </div>

        {/* Sources panel */}
        {showSources && sources.length > 0 && (
          <aside className="w-72 flex-shrink-0 overflow-y-auto p-4 animate-fade-in"
            style={{ background: 'var(--bg-secondary)', borderLeft: '1px solid var(--border)' }}>
            <h3 className="font-semibold text-sm mb-4">📖 Retrieved Sources</h3>
            <div className="space-y-3">
              {sources.map((s, i) => (
                <div key={i} className="glass-card p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Page {s.page}</span>
                    <span className="text-xs" style={{ color: 'var(--accent-purple-light)' }}>
                      {Math.round(s.score * 100)}% match
                    </span>
                  </div>
                  <div className="mastery-bar">
                    <div className="mastery-fill" style={{ width: `${s.score * 100}%`, background: 'var(--accent-purple)' }} />
                  </div>
                </div>
              ))}
            </div>
            <p className="text-xs mt-4" style={{ color: 'var(--text-muted)' }}>
              These sections from your document were used to generate the Socratic question
            </p>
          </aside>
        )}
      </div>
    </div>
  );
}
