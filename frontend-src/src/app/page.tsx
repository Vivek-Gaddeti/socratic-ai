'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import Link from 'next/link';

export default function HomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) router.push('/dashboard');
  }, [user, loading, router]);

  return (
    <main className="min-h-screen flex flex-col" style={{ background: 'var(--bg-primary)' }}>
      {/* Animated background blobs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 left-1/4 w-96 h-96 rounded-full opacity-10 blur-3xl animate-float"
          style={{ background: 'radial-gradient(circle, var(--accent-purple), transparent)' }} />
        <div className="absolute bottom-20 right-1/4 w-80 h-80 rounded-full opacity-10 blur-3xl animate-float"
          style={{ background: 'radial-gradient(circle, var(--accent-blue), transparent)', animationDelay: '1.5s' }} />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full opacity-5 blur-3xl"
          style={{ background: 'radial-gradient(circle, var(--accent-cyan), transparent)' }} />
      </div>

      {/* Nav */}
      <nav className="relative z-10 flex items-center justify-between px-8 py-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center text-lg"
            style={{ background: 'linear-gradient(135deg, var(--accent-purple), var(--accent-blue))' }}>
            🦉
          </div>
          <span className="font-bold text-xl gradient-text">SocraticAI</span>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/login">
            <button className="btn-secondary text-sm px-5 py-2.5">Sign in</button>
          </Link>
          <Link href="/register">
            <button className="btn-primary text-sm px-5 py-2.5">Get Started Free</button>
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative z-10 flex-1 flex flex-col items-center justify-center text-center px-6 py-24">
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium mb-8 animate-fade-in"
          style={{ background: 'rgba(124, 58, 237, 0.15)', border: '1px solid rgba(124, 58, 237, 0.3)', color: 'var(--accent-purple-light)' }}>
          <span className="w-2 h-2 rounded-full animate-pulse-glow"
            style={{ background: 'var(--accent-purple)' }} />
          Powered by Gemini AI + RAG + Multi-Agent System
        </div>

        <h1 className="text-6xl md:text-7xl font-black mb-6 leading-tight animate-fade-in-up"
          style={{ animationDelay: '0.1s', opacity: 0 }}>
          Learn by{' '}
          <span className="gradient-text">Discovery</span>
          <br />Not by <span style={{ color: 'var(--text-secondary)' }}>Memorization</span>
        </h1>

        <p className="text-xl max-w-2xl mb-10 leading-relaxed animate-fade-in-up"
          style={{ color: 'var(--text-secondary)', animationDelay: '0.2s', opacity: 0 }}>
          SocraticAI never gives you the answer. Instead, it asks the{' '}
          <strong style={{ color: 'var(--text-primary)' }}>right questions</strong> to guide
          you to discover truth yourself — just like Socrates did 2,400 years ago.
        </p>

        <div className="flex flex-wrap gap-4 justify-center animate-fade-in-up"
          style={{ animationDelay: '0.3s', opacity: 0 }}>
          <Link href="/register">
            <button className="btn-primary text-base px-8 py-4">
              🚀 Start Learning Free
            </button>
          </Link>
          <Link href="/login">
            <button className="btn-secondary text-base px-8 py-4">
              View Demo →
            </button>
          </Link>
        </div>

        {/* Feature badges */}
        <div className="flex flex-wrap gap-3 justify-center mt-12 animate-fade-in-up"
          style={{ animationDelay: '0.4s', opacity: 0 }}>
          {[
            { icon: '📚', text: 'Upload Any PDF' },
            { icon: '🤖', text: 'Multi-Agent AI' },
            { icon: '🧠', text: 'RAG-Powered' },
            { icon: '📊', text: 'Track Mastery' },
            { icon: '💡', text: 'Smart Hints' },
            { icon: '🎯', text: 'Adaptive Difficulty' },
          ].map(({ icon, text }) => (
            <span key={text} className="glass-card px-4 py-2 text-sm font-medium flex items-center gap-2"
              style={{ borderRadius: '30px', color: 'var(--text-secondary)' }}>
              {icon} {text}
            </span>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="relative z-10 px-8 py-20 max-w-6xl mx-auto w-full">
        <h2 className="text-3xl font-bold text-center mb-4">
          How <span className="gradient-text">SocraticAI</span> Works
        </h2>
        <p className="text-center mb-14" style={{ color: 'var(--text-secondary)' }}>
          A multi-agent AI system designed for deep understanding
        </p>

        <div className="grid md:grid-cols-3 gap-6">
          {[
            {
              step: '01',
              icon: '📄',
              title: 'Upload Your Material',
              desc: 'Upload any PDF — textbook, lecture notes, research paper. Our RAG pipeline chunks, embeds, and indexes it instantly.',
              color: 'var(--accent-purple)',
            },
            {
              step: '02',
              icon: '🦉',
              title: 'Socratic Dialogue Begins',
              desc: 'Instead of lecturing, SocraticAI asks probing questions. The Evaluator Agent scores your answers 0–100 in real-time.',
              color: 'var(--accent-blue)',
            },
            {
              step: '03',
              icon: '🏆',
              title: 'Achieve True Mastery',
              desc: 'Track your knowledge across all concepts. Get adaptive hints when stuck. Master topics through discovery, not rote memorization.',
              color: 'var(--accent-cyan)',
            },
          ].map(({ step, icon, title, desc, color }) => (
            <div key={step} className="glass-card p-8 relative overflow-hidden group">
              <div className="absolute top-4 right-6 text-6xl font-black opacity-5 group-hover:opacity-10 transition-opacity"
                style={{ color }}>
                {step}
              </div>
              <div className="text-4xl mb-5">{icon}</div>
              <h3 className="text-lg font-bold mb-3">{title}</h3>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{desc}</p>
              <div className="absolute bottom-0 left-0 right-0 h-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }} />
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="relative z-10 text-center py-20 px-6">
        <div className="glass-card max-w-2xl mx-auto p-12 glow-purple">
          <div className="text-5xl mb-6">🦉</div>
          <h2 className="text-3xl font-bold mb-4">
            Ready to <span className="gradient-text">truly understand</span>?
          </h2>
          <p className="mb-8" style={{ color: 'var(--text-secondary)' }}>
            Join learners who discover knowledge instead of memorizing it.
          </p>
          <Link href="/register">
            <button className="btn-primary text-base px-10 py-4 animate-pulse-glow">
              Start Your Journey →
            </button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 text-center py-8 text-sm" style={{ color: 'var(--text-muted)', borderTop: '1px solid var(--border)' }}>
        <p>SocraticAI — Built with Gemini AI, LangGraph, RAG & Next.js</p>
      </footer>
    </main>
  );
}
