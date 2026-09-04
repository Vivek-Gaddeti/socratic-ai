'use client';
import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/lib/api';
import Link from 'next/link';

interface Document { id: string; filename: string; status: string; topics: string[]; chunks_count: number; created_at: string; }
interface KnowledgeState { concept: string; mastery_score: number; attempts: number; document_id: string; }
interface Session { id: string; document_id: string; topic: string; created_at: string; }

export default function DashboardPage() {
  const { user, token, logout, loading: authLoading } = useAuth();
  const router = useRouter();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [knowledge, setKnowledge] = useState<KnowledgeState[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState('');
  const [activeTab, setActiveTab] = useState<'docs' | 'progress' | 'sessions'>('docs');
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!authLoading && !user) router.push('/login');
  }, [user, authLoading, router]);

  useEffect(() => {
    if (token) {
      loadAll();
      const interval = setInterval(loadDocuments, 5000); // poll for processing status
      return () => clearInterval(interval);
    }
  }, [token]);

  const loadAll = () => { loadDocuments(); loadKnowledge(); loadSessions(); };
  const loadDocuments = async () => { try { setDocuments(await api.getDocuments(token!)); } catch {} };
  const loadKnowledge = async () => { try { setKnowledge(await api.getKnowledgeState(token!)); } catch {} };
  const loadSessions = async () => { try { setSessions(await api.getSessions(token!)); } catch {} };

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(''), 3000); };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await api.uploadDocument(file, token!);
      showToast('📄 PDF uploaded! Processing...');
      loadDocuments();
    } catch (err: any) {
      showToast('❌ ' + (err.message || 'Upload failed'));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleDelete = async (id: string) => {
    await api.deleteDocument(id, token!);
    setDocuments(d => d.filter(x => x.id !== id));
    showToast('🗑️ Document deleted');
  };

  const startChat = async (docId?: string) => {
    const s = await api.startSession(token!, docId);
    router.push(`/chat/${s.session_id}`);
  };

  const getMasteryColor = (score: number) => {
    if (score >= 85) return 'var(--accent-purple)';
    if (score >= 60) return 'var(--accent-blue)';
    if (score >= 40) return 'var(--accent-yellow)';
    return '#ef4444';
  };

  if (authLoading || !user) return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg-primary)' }}>
      <div className="text-center">
        <div className="text-4xl mb-4 animate-float">🦉</div>
        <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--bg-primary)' }}>
      {/* Sidebar */}
      <aside className="sidebar w-64 flex-shrink-0 flex flex-col p-5">
        <Link href="/" className="flex items-center gap-3 mb-8">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center text-lg"
            style={{ background: 'linear-gradient(135deg, var(--accent-purple), var(--accent-blue))' }}>🦉</div>
          <span className="font-bold text-lg gradient-text">SocraticAI</span>
        </Link>

        <nav className="flex-1 space-y-1">
          {[
            { id: 'docs', icon: '📚', label: 'Documents' },
            { id: 'progress', icon: '📊', label: 'My Progress' },
            { id: 'sessions', icon: '💬', label: 'Sessions' },
          ].map(item => (
            <button key={item.id} onClick={() => setActiveTab(item.id as any)}
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all"
              style={{
                background: activeTab === item.id ? 'rgba(124,58,237,0.15)' : 'transparent',
                color: activeTab === item.id ? 'var(--accent-purple-light)' : 'var(--text-secondary)',
                border: activeTab === item.id ? '1px solid rgba(124,58,237,0.3)' : '1px solid transparent',
              }}>
              <span>{item.icon}</span> {item.label}
            </button>
          ))}
        </nav>

        <div className="mt-auto pt-4" style={{ borderTop: '1px solid var(--border)' }}>
          <div className="mb-3 px-3 py-2">
            <p className="text-sm font-medium">{user.name}</p>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{user.email}</p>
          </div>
          <button onClick={() => { logout(); router.push('/'); }}
            className="w-full btn-secondary text-sm py-2">Sign Out</button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8 overflow-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">
              {activeTab === 'docs' && '📚 Documents'}
              {activeTab === 'progress' && '📊 Knowledge Progress'}
              {activeTab === 'sessions' && '💬 Learning Sessions'}
            </h1>
            <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
              {activeTab === 'docs' && 'Upload PDFs to learn from them with Socratic AI'}
              {activeTab === 'progress' && 'Your mastery scores across all concepts'}
              {activeTab === 'sessions' && 'Continue or review past learning sessions'}
            </p>
          </div>
          <div className="flex gap-3">
            <button onClick={() => startChat()} className="btn-secondary text-sm px-4 py-2">
              💬 Free Chat
            </button>
            <button onClick={() => fileRef.current?.click()} className="btn-primary text-sm px-4 py-2" disabled={uploading}>
              {uploading ? (
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Uploading...
                </span>
              ) : '+ Upload PDF'}
            </button>
            <input ref={fileRef} type="file" accept=".pdf" onChange={handleUpload} className="hidden" />
          </div>
        </div>

        {/* Documents Tab */}
        {activeTab === 'docs' && (
          <div>
            {documents.length === 0 ? (
              <div className="glass-card p-16 text-center">
                <div className="text-6xl mb-6 animate-float">📄</div>
                <h3 className="text-xl font-bold mb-3">No documents yet</h3>
                <p className="mb-6" style={{ color: 'var(--text-secondary)' }}>
                  Upload a PDF to start a Socratic learning session
                </p>
                <button onClick={() => fileRef.current?.click()} className="btn-primary px-8 py-3">
                  Upload Your First PDF
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
                {documents.map((doc, i) => (
                  <div key={doc.id} className="glass-card p-6 group animate-fade-in-up"
                    style={{ animationDelay: `${i * 0.05}s`, opacity: 0 }}>
                    <div className="flex items-start justify-between mb-4">
                      <div className="text-3xl">📄</div>
                      <span className="text-xs px-2 py-1 rounded-full font-medium"
                        style={{
                          background: doc.status === 'ready' ? 'rgba(16,185,129,0.15)' : doc.status === 'processing' ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)',
                          color: doc.status === 'ready' ? '#10b981' : doc.status === 'processing' ? '#f59e0b' : '#ef4444',
                        }}>
                        {doc.status === 'ready' ? '✓ Ready' : doc.status === 'processing' ? '⟳ Processing' : '✗ Error'}
                      </span>
                    </div>
                    <h3 className="font-semibold mb-1 text-sm leading-snug line-clamp-2">{doc.filename}</h3>
                    <p className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>
                      {doc.chunks_count > 0 ? `${doc.chunks_count} chunks indexed` : 'Indexing...'}
                    </p>
                    {doc.topics?.length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-4">
                        {doc.topics.slice(0, 3).map(t => (
                          <span key={t} className="text-xs px-2 py-0.5 rounded-full"
                            style={{ background: 'rgba(124,58,237,0.15)', color: 'var(--accent-purple-light)' }}>
                            {t.slice(0, 20)}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="flex gap-2 mt-auto">
                      <button onClick={() => startChat(doc.id)} disabled={doc.status !== 'ready'}
                        className="btn-primary flex-1 text-xs py-2 disabled:opacity-40">
                        🦉 Learn
                      </button>
                      <button onClick={() => handleDelete(doc.id)}
                        className="btn-secondary text-xs py-2 px-3 opacity-0 group-hover:opacity-100 transition-opacity">
                        🗑️
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Progress Tab */}
        {activeTab === 'progress' && (
          <div>
            {knowledge.length === 0 ? (
              <div className="glass-card p-16 text-center">
                <div className="text-6xl mb-6 animate-float">📊</div>
                <h3 className="text-xl font-bold mb-3">No progress yet</h3>
                <p style={{ color: 'var(--text-secondary)' }}>Start a learning session to track your mastery</p>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Summary stats */}
                <div className="grid grid-cols-3 gap-4 mb-6">
                  {[
                    { label: 'Concepts Studied', value: knowledge.length, icon: '🧠' },
                    { label: 'Avg Mastery', value: `${Math.round(knowledge.reduce((a, k) => a + k.mastery_score, 0) / knowledge.length)}%`, icon: '📈' },
                    { label: 'Mastered (>85%)', value: knowledge.filter(k => k.mastery_score >= 85).length, icon: '🏆' },
                  ].map(stat => (
                    <div key={stat.label} className="glass-card p-5 text-center">
                      <div className="text-2xl mb-2">{stat.icon}</div>
                      <div className="text-2xl font-bold mb-1">{stat.value}</div>
                      <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{stat.label}</div>
                    </div>
                  ))}
                </div>

                {/* Concept list */}
                <div className="glass-card overflow-hidden">
                  <div className="p-4" style={{ borderBottom: '1px solid var(--border)' }}>
                    <h3 className="font-semibold">All Concepts</h3>
                  </div>
                  <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
                    {knowledge.map((k, i) => (
                      <div key={i} className="flex items-center gap-4 p-4 hover:bg-opacity-50 transition-colors"
                        style={{ background: 'transparent' }}
                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-sm truncate">{k.concept}</p>
                          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{k.attempts} attempts</p>
                        </div>
                        <div className="w-40">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>Mastery</span>
                            <span className="text-xs font-bold" style={{ color: getMasteryColor(k.mastery_score) }}>
                              {Math.round(k.mastery_score)}%
                            </span>
                          </div>
                          <div className="mastery-bar">
                            <div className="mastery-fill" style={{
                              width: `${k.mastery_score}%`,
                              background: `linear-gradient(90deg, ${getMasteryColor(k.mastery_score)}, ${getMasteryColor(k.mastery_score)}88)`,
                            }} />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Sessions Tab */}
        {activeTab === 'sessions' && (
          <div>
            {sessions.length === 0 ? (
              <div className="glass-card p-16 text-center">
                <div className="text-6xl mb-6 animate-float">💬</div>
                <h3 className="text-xl font-bold mb-3">No sessions yet</h3>
                <p style={{ color: 'var(--text-secondary)' }}>Your learning conversations will appear here</p>
              </div>
            ) : (
              <div className="space-y-3">
                {sessions.map((s, i) => (
                  <div key={s.id} className="glass-card p-5 flex items-center gap-4 animate-fade-in-up cursor-pointer"
                    style={{ animationDelay: `${i * 0.05}s`, opacity: 0 }}
                    onClick={() => router.push(`/chat/${s.id}`)}>
                    <div className="w-10 h-10 rounded-lg flex items-center justify-center text-xl flex-shrink-0"
                      style={{ background: 'rgba(124,58,237,0.15)' }}>💬</div>
                    <div className="flex-1">
                      <p className="font-medium text-sm">{s.topic || 'General Session'}</p>
                      <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                        {new Date(s.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                    <span className="text-sm" style={{ color: 'var(--text-muted)' }}>→</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
