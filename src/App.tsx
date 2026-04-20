import { useState, useEffect, useRef, useCallback } from 'react';
import type { AuthUser, AppSettings, PastMeeting, Suggestion } from './api';
import {
  getUser, signIn, signUp, signOut,
  startMeeting, endMeeting,
  getSuggestions, streamSuggestion,
  pushTranscriptLine,
  getHealth, type HealthStatus,
  getSettings, saveSettings,
  getPastMeetings, saveMeeting,
  uploadDocument, queryRAG,
  exportNotesMD, exportNotesPDF,
} from './api';
import { AutoListener, checkBrowserSupport, type TranscriptEvent } from './audio';

// ─── Types ────────────────────────────────────────────────────────────────────
type View = 'landing' | 'auth' | 'dashboard' | 'meeting' | 'notes' | 'settings' | 'docs';

// ─── Root ─────────────────────────────────────────────────────────────────────
export default function App() {
  const [user, setUser]   = useState<AuthUser | null>(getUser);
  const [view, setView]   = useState<View>(user ? 'dashboard' : 'landing');
  const [toast, setToast] = useState('');
  const [health, setHealth] = useState<HealthStatus>({ online: false, whisper: false, llm: false, rag: false, model: 'demo' });

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(''), 2300); };

  // Poll health
  useEffect(() => {
    const check = () => getHealth().then(setHealth);
    check();
    const id = setInterval(check, 8000);
    return () => clearInterval(id);
  }, []);

  const handleSignIn = async (email: string, pw: string) => {
    const u = await signIn(email, pw);
    setUser(u); setView('dashboard'); showToast(`Welcome back, ${u.name.split(' ')[0]}!`);
  };
  const handleSignUp = async (email: string, pw: string, name: string) => {
    const u = await signUp(email, pw, name);
    setUser(u); setView('dashboard'); showToast(`Account created! Welcome ${u.name.split(' ')[0]}.`);
  };
  const handleSignOut = () => { signOut(); setUser(null); setView('landing'); };

  return (
    <>
      {view === 'landing' && <LandingPage onGetStarted={() => setView('auth')} />}
      {view === 'auth'    && <AuthScreen onSignIn={handleSignIn} onSignUp={handleSignUp} onBack={() => setView('landing')} />}
      {(view !== 'landing' && view !== 'auth') && (
        <AppShell user={user!} view={view} setView={setView} health={health} onSignOut={handleSignOut} showToast={showToast}>
          {view === 'dashboard' && <DashboardScreen user={user!} setView={setView} />}
          {view === 'meeting'   && <MeetingRoom settings={getSettings()} health={health} showToast={showToast} onEnd={({ id, dur, sugg, title }) => { saveMeeting({ id, title, date: 'Just now', duration: dur, model: getSettings().model, suggestions: sugg }); setView('notes'); }} />}
          {view === 'notes'     && <NotesScreen meetings={getPastMeetings()} showToast={showToast} />}
          {view === 'settings'  && <SettingsScreen showToast={showToast} />}
          {view === 'docs'      && <DocsScreen showToast={showToast} />}
        </AppShell>
      )}
      {toast && <div className="toast">{toast}</div>}
    </>
  );
}

// ─── Landing Page ─────────────────────────────────────────────────────────────
function LandingPage({ onGetStarted }: { onGetStarted: () => void }) {
  return (
    <div className="saas-root">
      {/* Nav */}
      <nav className="saas-nav">
        <div className="saas-logo">◈ MeetAI</div>
        <div className="nav-tabs" style={{ display: 'flex', gap: 8 }}>
          <a href="#how" className="nav-tab">How it works</a>
          <a href="#pricing" className="nav-tab">Pricing</a>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn-ghost" onClick={onGetStarted}>Sign in</button>
          <button className="btn-primary" onClick={onGetStarted}>Get started free</button>
        </div>
      </nav>

      {/* Hero */}
      <section className="saas-hero">
        <div className="hero-badge">🛡️ Invisible to screen sharing · Zero typing · Real AI</div>
        <h1 className="hero-title">
          Your AI co-pilot<br/>
          <span className="grad">invisible in every call</span>
        </h1>
        <p className="hero-sub">
          MeetAI listens to your calls automatically, transcribes every word, and surfaces perfect AI answers the moment they stop talking — no typing, no clicking. Just the right words, when you need them.
        </p>
        <div className="hero-cta">
          <button className="btn-primary btn-xl" onClick={onGetStarted}>
            🎙️ Start for free
          </button>
          <button className="btn-secondary" style={{ padding: '16px 28px', fontSize: 15 }}>
            ▶ Watch 90s demo
          </button>
        </div>

        {/* Live preview */}
        <div className="hero-preview">
          <div className="preview-bar">
            <div className="preview-dot" style={{ background: '#ef4444' }} />
            <div className="preview-dot" style={{ background: '#f59e0b' }} />
            <div className="preview-dot" style={{ background: '#22c55e' }} />
            <div style={{ flex: 1, textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>meetai.app — LIVE · 08:42</div>
            <div className="pill pill-live" style={{ fontSize: 10 }}>● LIVE</div>
          </div>
          <div className="preview-screen">
            {/* Transcript side */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ fontSize: 10, letterSpacing: 2, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase' }}>Live Transcript</div>
              {[
                { sp: 'Them', text: 'Tell me about your experience with distributed systems at scale.' },
                { sp: 'You', text: 'We operated Kafka clusters across 3 regions handling 2M events/sec…' },
                { sp: 'Them', text: 'How did you handle partition rebalancing without downtime? ⠶ speaking…', muted: true },
              ].map((l, i) => (
                <div key={i} style={{ borderLeft: `2px solid ${l.sp === 'You' ? 'var(--tertiary-accent)' : 'var(--primary-accent)'}`, paddingLeft: 12 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: l.sp === 'You' ? 'var(--tertiary)' : 'var(--primary)', marginBottom: 4, textTransform: 'uppercase' }}>{l.sp}</div>
                  <div style={{ fontSize: 12, color: l.muted ? 'var(--text-subtle)' : 'var(--text-secondary)', fontStyle: l.muted ? 'italic' : 'normal' }}>{l.text}</div>
                </div>
              ))}
            </div>
            {/* Suggestions side */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontSize: 10, letterSpacing: 2, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase' }}>AI Suggestions · Auto</div>
              {[
                { label: 'Best Answer', conf: 94, text: 'We used a rolling restart strategy: incremented one broker at a time, allowed leader election to stabilize before touching the next node. For large partitions we pre-allocated replicas to avoid bottlenecks.' },
                { label: 'More Detail', conf: 87, text: 'Monitoring was via Burrow + Prometheus; we set up lag alerts at partition level…' },
              ].map((s, i) => (
                <div key={i} className="sugg-card" style={{ animationDelay: `${i * 0.1}s` }}>
                  <div className="sugg-header">
                    <span style={{ fontSize: 14 }}>{i === 0 ? '💬' : '📚'}</span>
                    <span className="sugg-label">{s.label}</span>
                    <span className="sugg-conf">{s.conf}%</span>
                  </div>
                  <p className="sugg-text">{s.text}</p>
                  {i === 0 && <button className="sugg-copy-btn">Copy ↗</button>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="saas-section" id="how">
        <div style={{ textAlign: 'center' }}>
          <div className="section-tag">HOW IT WORKS</div>
          <h2 className="section-title">Three steps. <span style={{ color: 'var(--primary)' }}>Zero effort.</span></h2>
          <p style={{ color: 'var(--text-muted)', maxWidth: 500, margin: '0 auto', fontSize: 15 }}>No extensions. No virtual audio drivers. Works in any browser tab alongside Zoom, Teams, or Google Meet.</p>
        </div>
        <div className="steps-grid">
          {[
            { num: '01', icon: '🎙️', title: 'Click "Start Meeting"', desc: 'Allow mic access + share your meeting tab audio. That\'s it. MeetAI begins listening immediately.' },
            { num: '02', icon: '✍️', title: 'It transcribes everything', desc: 'Both sides of the conversation appear in real-time. Chrome\'s built-in speech engine — no API cost, zero latency.' },
            { num: '03', icon: '⚡', title: 'AI answers appear automatically', desc: 'The moment they stop talking, AI suggestions slide in. Read, speak, done. No keyboard needed.' },
            { num: '04', icon: '🛡️', title: 'Completely invisible', desc: 'The overlay is excluded from all screen capture. Your interviewer or client sees nothing but your face.' },
          ].map(s => (
            <div key={s.num} className="step-card">
              <div className="step-num">{s.num}</div>
              <div className="step-icon">{s.icon}</div>
              <div className="step-title">{s.title}</div>
              <div className="step-desc">{s.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section className="saas-section" id="pricing">
        <div style={{ textAlign: 'center' }}>
          <div className="section-tag">PRICING</div>
          <h2 className="section-title">Simple, transparent pricing</h2>
        </div>
        <div className="pricing-grid">
          {[
            { tier: 'FREE', price: '$0', desc: 'Get started — no credit card needed.', features: ['5 meetings/month', 'Browser auto-transcription', 'AI suggestions (demo)', '1 document upload', 'Markdown export'], cta: 'Start free', featured: false },
            { tier: 'PRO', price: '$12', desc: 'For individuals who interview or sell regularly.', features: ['100 meetings/month', 'Unlimited transcription', 'Claude / GPT-4 / Gemini', 'Unlimited document RAG', 'PDF + DOCX export', 'Meeting notes & summaries', 'Invisible desktop overlay'], cta: 'Start Pro trial', featured: true },
            { tier: 'TEAM', price: '$49', desc: 'For teams and professionals at scale.', features: ['Unlimited meetings', 'Everything in Pro', 'Team shared context docs', 'Custom AI personas', 'Slack / Notion export', 'Admin dashboard', 'SSO & SCIM'], cta: 'Contact sales', featured: false },
          ].map(p => (
            <div key={p.tier} className={`pricing-card ${p.featured ? 'featured' : ''}`}>
              {p.featured && <div className="pricing-badge">⭐ Most popular</div>}
              <div className="pricing-tier">{p.tier}</div>
              <div className="pricing-price">{p.price}<span>/mo</span></div>
              <div className="pricing-desc">{p.desc}</div>
              <ul className="pricing-features">
                {p.features.map(f => <li key={f}>{f}</li>)}
              </ul>
              <button className={p.featured ? 'btn-primary' : 'btn-secondary'} style={{ width: '100%', justifyContent: 'center' }} onClick={onGetStarted}>{p.cta}</button>
            </div>
          ))}
        </div>
      </section>

      <footer className="saas-footer">
        <div style={{ marginBottom: 8, color: 'var(--primary)', fontWeight: 700, fontFamily: 'var(--font-display)' }}>◈ MeetAI</div>
        <div>© 2026 MeetAI. Built with faster-whisper, LiteLLM, ChromaDB, and React.</div>
      </footer>
    </div>
  );
}

// ─── Auth Screen ──────────────────────────────────────────────────────────────
function AuthScreen({ onSignIn, onSignUp, onBack }: { onSignIn: (e: string, p: string) => void; onSignUp: (e: string, p: string, n: string) => void; onBack: () => void }) {
  const [mode, setMode] = useState<'in' | 'up'>('in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      if (mode === 'in') await onSignIn(email, password);
      else await onSignUp(email, password, name || email.split('@')[0]);
    } catch (err: any) {
      setError(err?.message ?? 'Something went wrong');
    } finally { setLoading(false); }
  };

  return (
    <div className="auth-root">
      <div className="auth-bg-glow" style={{ top: '-100px', left: '50%', transform: 'translateX(-50%)' }} />
      <div className="auth-card">
        <div className="auth-logo" style={{ justifyContent: 'space-between' }}>
          <span>◈ MeetAI</span>
          <button className="btn-ghost" style={{ fontSize: 12 }} onClick={onBack}>← Back</button>
        </div>
        <h2 className="auth-title">{mode === 'in' ? 'Welcome back' : 'Create your account'}</h2>
        <p className="auth-sub">{mode === 'in' ? 'Sign in to continue to MeetAI' : 'Get started free — no credit card needed'}</p>

        <form onSubmit={handleSubmit}>
          {mode === 'up' && (
            <div className="form-group">
              <label className="form-label">Full name</label>
              <input className="form-input" placeholder="Alex Chen" value={name} onChange={e => setName(e.target.value)} required />
            </div>
          )}
          <div className="form-group">
            <label className="form-label">Email</label>
            <input className="form-input" type="email" placeholder="you@company.com" value={email} onChange={e => setEmail(e.target.value)} required />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input className="form-input" type="password" placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} required minLength={6} />
          </div>
          {error && <div style={{ fontSize: 13, color: 'var(--error)', marginBottom: 12 }}>{error}</div>}
          <button className="btn-primary" style={{ width: '100%', justifyContent: 'center', marginTop: 8 }} disabled={loading}>
            {loading ? '⏳ Please wait…' : mode === 'in' ? '→ Sign in' : '→ Create account'}
          </button>
        </form>

        <div className="auth-divider"><span>or demo without account</span></div>
        <button className="btn-secondary" style={{ width: '100%', justifyContent: 'center' }} onClick={() => onSignIn('demo@meetai.app', 'demo')}>
          🎙️ Try demo instantly
        </button>

        <div className="auth-switch">
          {mode === 'in' ? (
            <>Don't have an account? <button onClick={() => setMode('up')}>Sign up free</button></>
          ) : (
            <>Already have an account? <button onClick={() => setMode('in')}>Sign in</button></>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── App Shell ────────────────────────────────────────────────────────────────────
function AppShell({ user, view, setView, health, onSignOut, showToast, children }: { user: AuthUser; view: View; setView: (v: View) => void; health: HealthStatus; onSignOut: () => void; showToast: (m: string) => void; children: React.ReactNode }) {
  if (view === 'meeting') return <>{children}</>;

  const tabs: { id: View; label: string; icon: string }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: '⊞' },
    { id: 'notes',     label: 'Notes',     icon: '📋' },
    { id: 'docs',      label: 'Documents', icon: '📁' },
    { id: 'settings',  label: 'Settings',  icon: '⚙️' },
  ];

  return (
    <div className="app-root">
      <nav className="app-nav">
        <div className="nav-logo">◈ MeetAI</div>
        <div className="nav-tabs">
          {tabs.map(t => (
            <button key={t.id} className={`nav-tab ${view === t.id ? 'active' : ''}`} onClick={() => setView(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="nav-user">
          <div className="pill" style={{ fontSize: 10, color: health.online ? 'var(--success)' : 'var(--text-muted)', background: health.online ? 'var(--success-10)' : 'var(--glass-bg)', border: `1px solid ${health.online ? 'rgba(34,197,94,0.3)' : 'var(--ghost-border)'}` }}>
            {health.online ? '● API' : '○ Demo'}
          </div>
          <div className="avatar">{user.name.slice(0, 2).toUpperCase()}</div>
          <button className="btn-ghost" style={{ fontSize: 12 }} onClick={onSignOut}>Sign out</button>
        </div>
      </nav>
      <div className="app-content">{children}</div>
    </div>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────────
function DashboardScreen({ user, setView }: { user: AuthUser; setView: (v: View) => void }) {
  const meetings = getPastMeetings();
  const totalSugg = meetings.reduce((a, m) => a + m.suggestions, 0);

  return (
    <div>
      <div className="dash-header">
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
          {new Date().toLocaleDateString('en', { weekday: 'long', month: 'long', day: 'numeric' })}
        </div>
        <div className="dash-title">Good {new Date().getHours() < 12 ? 'morning' : 'afternoon'}, {user.name.split(' ')[0]} 👋</div>
        <div style={{ fontSize: 14, color: 'var(--text-muted)' }}>
          {user.meetingsLimit - user.meetingsUsed} meetings remaining this month
        </div>
      </div>

      {/* Start meeting CTA */}
      <div style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.12) 0%, rgba(139,92,246,0.10) 100%)', border: '1px solid var(--primary-30)', borderRadius: 'var(--radius-xl)', padding: '32px 36px', marginBottom: 28, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 20 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 800, marginBottom: 6 }}>Ready to start a meeting?</div>
          <div style={{ fontSize: 14, color: 'var(--text-muted)', maxWidth: 400 }}>MeetAI will listen automatically and surface AI answers the instant they stop talking.</div>
        </div>
        <button className="btn-primary btn-xl" onClick={() => setView('meeting')}>
          🎙️ Start meeting
        </button>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        {[
          { icon: '🎙️', value: user.meetingsUsed.toString(), label: 'Meetings this month' },
          { icon: '⚡', value: totalSugg.toString(), label: 'AI suggestions used' },
          { icon: '📋', value: meetings.length.toString(), label: 'Notes saved' },
          { icon: '🛡️', value: '100%', label: 'Invisible to capture' },
        ].map(s => (
          <div key={s.label} className="stat-card">
            <div className="stat-icon">{s.icon}</div>
            <div className="stat-value">{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Recent meetings */}
      <div className="section-label">RECENT MEETINGS</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {meetings.slice(0, 5).map(m => (
          <div key={m.id} className="glass-card" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 16, cursor: 'pointer', transition: 'border-color 200ms' }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--ghost-border-hover)')}
            onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--ghost-border)')}>
            <div style={{ width: 40, height: 40, borderRadius: 12, background: 'var(--primary-10)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, flexShrink: 0 }}>🤖</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.title}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{m.date} · {m.duration} · {m.model} · {m.suggestions} suggestions</div>
            </div>
            <div style={{ fontSize: 18, color: 'var(--text-subtle)' }}>›</div>
          </div>
        ))}
      </div>

      {/* Setup prompt */}
      <div style={{ marginTop: 28, background: 'var(--warning-10)', border: '1px solid rgba(245,158,11,0.25)', borderRadius: 'var(--radius-lg)', padding: '16px 20px', fontSize: 13, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 20 }}>💡</span>
        <div>
          <strong style={{ color: 'var(--warning)' }}>Tip:</strong> Go to <strong>Settings</strong> to write your context prompt and add your API key for real AI answers. Upload docs in <strong>Documents</strong> to ground answers in your actual experience.
        </div>
      </div>
    </div>
  );
}

// ─── MEETING ROOM — Zero interaction, fully automatic ────────────────────────
type TxLine = TranscriptEvent & { id: string };

interface MeetingRoomProps {
  settings: AppSettings;
  health: HealthStatus;
  showToast: (m: string) => void;
  onEnd: (data: { id: string; dur: string; sugg: number; title: string }) => void;
}

function MeetingRoom({ settings, health, showToast, onEnd }: MeetingRoomProps) {
  const [phase, setPhase] = useState<'perm' | 'live' | 'ending'>('perm');
  const [status, setStatus] = useState('Initializing…');
  const [sessionId, setSessionId] = useState('');
  const [elapsed, setElapsed] = useState(0);
  const [transcript, setTranscript] = useState<TxLine[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [streaming, setStreaming] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [suggCount, setSuggCount] = useState(0);
  const [micOk, setMicOk] = useState(false);
  const [sysOk, setSysOk] = useState(false);
  const [waves, setWaves] = useState<number[]>(Array(40).fill(3));

  const listenerRef = useRef<AutoListener | null>(null);
  const stopStreamRef = useRef<(() => void) | null>(null);
  const txEndRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const waveRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startRef = useRef(Date.now());

  // Format elapsed time
  const fmtTime = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  // Auto-scroll transcript
  useEffect(() => { txEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [transcript]);

  // Timer
  useEffect(() => {
    if (phase !== 'live') return;
    timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [phase]);

  // Waveform animation
  useEffect(() => {
    waveRef.current = setInterval(() => {
      setWaves(w => w.map(() => micOk ? 3 + Math.random() * 28 : 3));
    }, 80);
    return () => { if (waveRef.current) clearInterval(waveRef.current); };
  }, [micOk]);

  // Trigger AI when they pause
  const handleSilence = useCallback(async (utterance: string) => {
    if (!utterance.trim() || isThinking) return;
    setIsThinking(true);
    setSuggestions([]);
    setStreaming('');

    // If backend online — stream first suggestion
    if (health.online) {
      let buffer = '';
      stopStreamRef.current = streamSuggestion(
        utterance, sessionId, settings.model,
        (token) => { buffer += token; setStreaming(buffer); },
        async () => {
          setStreaming('');
          setIsThinking(false);
          // Get full ranked suggestions
          const suggs = await getSuggestions(utterance, sessionId, settings.model, settings.contextPrompt);
          setSuggestions(suggs);
          setSuggCount(c => c + suggs.length);
        },
      );
    } else {
      // Demo mode
      await new Promise(r => setTimeout(r, 600));
      const suggs = await getSuggestions(utterance, sessionId, settings.model, settings.contextPrompt);
      setSuggestions(suggs);
      setSuggCount(c => c + suggs.length);
      setIsThinking(false);
    }
  }, [health.online, sessionId, settings, isThinking]);

  // Start listening
  const startListening = async () => {
    const sup = checkBrowserSupport();
    if (!sup.speechRecognition) {
      showToast('⚠️ Use Chrome or Edge for voice transcription');
      return;
    }

    const id = `mtg_${Date.now()}`;
    setSessionId(id);
    await startMeeting(settings.model, settings.contextPrompt);

    const listener = new AutoListener({
      onTranscript: (ev) => {
        if (!ev.final) {
          // Update interim line for speaker
          setTranscript(prev => {
            const last = prev[prev.length - 1];
            if (last && !last.final && last.speaker === ev.speaker) {
              return [...prev.slice(0, -1), { ...ev, id: last.id }];
            }
            return [...prev, { ...ev, id: `tx_${Date.now()}_${Math.random()}` }];
          });
        } else {
          setTranscript(prev => {
            const last = prev[prev.length - 1];
            if (last && !last.final && last.speaker === ev.speaker) {
              const updated = { ...ev, id: last.id };
              pushTranscriptLine(id, ev.speaker, ev.text).catch(() => {});
              return [...prev.slice(0, -1), updated];
            }
            pushTranscriptLine(id, ev.speaker, ev.text).catch(() => {});
            return [...prev, { ...ev, id: `tx_${Date.now()}_${Math.random()}` }];
          });
        }
      },
      onSilenceAfterThem: handleSilence,
      onStatus: setStatus,
      silenceMs: settings.silenceMs,
    });

    const { micOk, sysOk } = await listener.start();
    listenerRef.current = listener;
    setMicOk(micOk);
    setSysOk(sysOk);
    setPhase('live');
    startRef.current = Date.now();
    showToast(micOk ? '🎙️ Listening — AI will respond automatically' : '❌ Mic access denied');
  };

  // End meeting
  const handleEnd = async () => {
    setPhase('ending');
    listenerRef.current?.stop();
    stopStreamRef.current?.();
    if (timerRef.current) clearInterval(timerRef.current);
    const dur = fmtTime(elapsed);
    const { summary } = await endMeeting(sessionId).catch(() => ({ summary: '', actions: [] }));
    if (summary) localStorage.setItem('meetai_last_summary', summary);
    localStorage.setItem('meetai_last_transcript', JSON.stringify(transcript));
    onEnd({ id: sessionId, dur, sugg: suggCount, title: 'Meeting · ' + new Date().toLocaleDateString() });
  };

  const copySuggestion = (text: string) => {
    navigator.clipboard.writeText(text).then(() => showToast('✓ Copied to clipboard'));
  };

  // ── Permission screen ──────────────────────────────────────────────────────
  if (phase === 'perm') {
    return (
      <div className="permission-overlay">
        <div className="permission-card">
          <div className="perm-icon">🎙️</div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 24, marginBottom: 12 }}>
            Allow microphone access
          </h2>
          <p style={{ fontSize: 14, color: 'var(--text-muted)', lineHeight: 1.65, marginBottom: 10 }}>
            MeetAI needs your microphone to transcribe the conversation. When prompted, also share your <strong style={{ color: 'var(--text-secondary)' }}>meeting tab audio</strong> so it can hear the other person.
          </p>
          <p style={{ fontSize: 12, color: 'var(--text-subtle)', marginBottom: 28 }}>
            No audio is recorded or stored in the cloud. Everything runs in your browser.
          </p>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
            <button className="btn-primary btn-xl" onClick={startListening}>
              🎙️ Allow & Start Listening
            </button>
          </div>
          <div style={{ marginTop: 16, fontSize: 12, color: 'var(--text-subtle)' }}>
            {checkBrowserSupport().speechRecognition ? '✓ Browser supports voice recognition' : '⚠️ Please use Chrome or Edge'}
          </div>
        </div>
      </div>
    );
  }

  // ── Live session ───────────────────────────────────────────────────────────
  const SUGG_ICONS: Record<string, string> = { answer: '💬', detail: '📚', followup: '🔄', clarify: '🎯' };

  return (
    <div className="meeting-room">
      {/* Top bar */}
      <div className="meeting-topbar">
        <div className="live-dot" />
        <div className="timer-display">{fmtTime(elapsed)}</div>
        <div className="status-chip">{sysOk ? '🎙️+🔊 Dual audio' : '🎙️ Mic only'}</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', flex: 1 }}>{status}</div>
        <div className="pill pill-primary" style={{ fontSize: 10 }}>{settings.model.toUpperCase()}</div>
        <button className="btn-danger" onClick={handleEnd} disabled={phase === 'ending'}>
          {phase === 'ending' ? '⏳ Saving…' : '■ End'}
        </button>
      </div>

      {/* Body */}
      <div className="meeting-body">
        {/* Left: Transcript */}
        <div className="transcript-panel">
          <div className="panel-header">Live Transcript · {transcript.filter(t => t.final).length} lines</div>
          <div className="transcript-scroll">
            {transcript.length === 0 ? (
              <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-subtle)', fontSize: 13 }}>
                <div style={{ fontSize: 32, marginBottom: 12 }}>👂</div>
                Listening… speak naturally, transcription appears here.
              </div>
            ) : (
              transcript.map(line => (
                <div key={line.id} className="tx-line">
                  <div className="tx-meta">
                    <span className={line.speaker === 'You' ? 'tx-speaker-you' : 'tx-speaker-them'}>{line.speaker}</span>
                    <span className="tx-time">{line.time}</span>
                  </div>
                  <div className={`tx-text ${!line.final ? 'interim' : ''}`}>{line.text}</div>
                </div>
              ))
            )}
            {isThinking && (
              <div className="tx-thinking">
                <div className="think-dots">
                  <div className="think-dot" /><div className="think-dot" /><div className="think-dot" />
                </div>
                AI is composing suggestions…
              </div>
            )}
            <div ref={txEndRef} />
          </div>

          {/* Waveform */}
          <div className="wave-bar">
            {waves.map((h, i) => (
              <div key={i} className="wave-segment" style={{ height: `${h}px` }} />
            ))}
          </div>
        </div>

        {/* Right: Suggestions */}
        <div className="suggestion-panel">
          <div className="panel-header">
            AI Suggestions · {suggCount} used
            {suggestions.length > 0 && (
              <span style={{ marginLeft: 8, fontWeight: 400, fontSize: 10, background: 'var(--success-10)', color: 'var(--success)', padding: '2px 6px', borderRadius: 4 }}>AUTO</span>
            )}
          </div>

          <div className="sugg-scroll">
            {/* Streaming card */}
            {streaming && (
              <div className="sugg-streaming">
                <div className="sugg-header">
                  <span className="sugg-icon">⚡</span>
                  <span className="sugg-label">Generating…</span>
                  <span className="model-badge">{settings.model}</span>
                </div>
                <p className="sugg-text">{streaming}<span className="stream-cursor" /></p>
              </div>
            )}

            {/* Final suggestions */}
            {suggestions.map((s, i) => (
              <div key={i} className="sugg-card" style={{ animationDelay: `${i * 0.07}s` }}>
                <div className="sugg-header">
                  <span className="sugg-icon">{SUGG_ICONS[s.type] ?? '💬'}</span>
                  <span className="sugg-label">{s.type === 'answer' ? 'Best Answer' : s.type === 'detail' ? 'More Detail' : s.type === 'followup' ? 'Follow-up' : 'Clarify'}</span>
                  <span className="sugg-conf">{s.confidence}%</span>
                </div>
                <p className="sugg-text">{s.text}</p>
                <div className="sugg-actions">
                  <button className="sugg-copy-btn" onClick={() => copySuggestion(s.text)}>Copy ↗</button>
                </div>
              </div>
            ))}

            {/* Empty state */}
            {!streaming && suggestions.length === 0 && !isThinking && (
              <div className="sugg-empty">
                <div className="sugg-empty-icon">⚡</div>
                <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-secondary)' }}>Waiting for them to speak</div>
                <div style={{ fontSize: 13, color: 'var(--text-subtle)', lineHeight: 1.6 }}>
                  AI suggestions appear here automatically when they stop talking.<br />No typing or clicking needed.
                </div>
                {!sysOk && (
                  <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-subtle)', background: 'var(--warning-10)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 8, padding: '10px 14px', textAlign: 'left', lineHeight: 1.6 }}>
                    💡 <strong style={{ color: 'var(--warning)' }}>Tip:</strong> For the other person's voice, click "Share tab" in the permission dialog and select your Zoom/Meet tab. Or restart the meeting and choose to share tab audio.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Notes Screen ─────────────────────────────────────────────────────────────
function NotesScreen({ meetings, showToast }: { meetings: PastMeeting[]; showToast: (m: string) => void }) {
  const [selected, setSelected] = useState(meetings[0]?.id ?? '');
  const lastSummary = localStorage.getItem('meetai_last_summary') ?? '';
  const lastTx: TxLine[] = (() => { try { return JSON.parse(localStorage.getItem('meetai_last_transcript') ?? '[]'); } catch { return []; } })();

  const mtg = meetings.find(m => m.id === selected);

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div className="section-label">MEETING NOTES</div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 22 }}>Past sessions</h2>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn-ghost" onClick={() => { exportNotesMD(lastSummary || (mtg?.summary ?? ''), mtg?.title ?? 'Notes'); showToast('✓ Exported as Markdown'); }}>↓ MD</button>
          <button className="btn-ghost" onClick={async () => { const ok = await exportNotesPDF(selected); showToast(ok ? '✓ PDF downloaded' : '⚠️ Start backend for PDF export'); }}>↓ PDF</button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 20 }}>
        {/* Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {meetings.map(m => (
            <button key={m.id} onClick={() => setSelected(m.id)} style={{ background: selected === m.id ? 'var(--primary-10)' : 'var(--glass-bg)', border: `1px solid ${selected === m.id ? 'var(--primary-30)' : 'var(--ghost-border)'}`, borderRadius: 'var(--radius-md)', padding: '12px 14px', textAlign: 'left', cursor: 'pointer', transition: 'all 150ms' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: selected === m.id ? 'var(--primary)' : 'var(--text-primary)', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.title}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{m.date} · {m.duration}</div>
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="notes-card">
          {mtg ? (
            <>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 18, marginBottom: 4 }}>{mtg.title}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 20 }}>{mtg.date} · {mtg.duration} · {mtg.model} · {mtg.suggestions} AI suggestions</div>
              <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.75, whiteSpace: 'pre-wrap' }}>
                {selected === meetings[0]?.id && lastSummary ? lastSummary : mtg.summary ?? 'No summary available.'}
              </div>
              {selected === meetings[0]?.id && lastTx.length > 0 && (
                <>
                  <div className="section-label" style={{ marginTop: 24 }}>TRANSCRIPT</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxHeight: 360, overflowY: 'auto' }}>
                    {lastTx.filter(t => t.final).map((t, i) => (
                      <div key={i} style={{ borderLeft: `2px solid ${t.speaker === 'You' ? 'var(--tertiary-accent)' : 'var(--primary-accent)'}`, paddingLeft: 12 }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: t.speaker === 'You' ? 'var(--tertiary)' : 'var(--primary)', textTransform: 'uppercase', marginBottom: 2 }}>{t.speaker} · {t.time}</div>
                        <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{t.text}</div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          ) : (
            <div style={{ textAlign: 'center', color: 'var(--text-subtle)', padding: 40 }}>Select a meeting to view notes</div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Settings Screen ──────────────────────────────────────────────────────────
function SettingsScreen({ showToast }: { showToast: (m: string) => void }) {
  const [s, setS] = useState<AppSettings>(getSettings);
  const update = (patch: Partial<AppSettings>) => { const n = { ...s, ...patch }; setS(n); saveSettings(n); };

  const MODELS = [
    { id: 'claude', label: 'Claude Sonnet', desc: 'Best for nuanced, human-like answers' },
    { id: 'gpt-4', label: 'GPT-4o', desc: 'Broad knowledge, very fast' },
    { id: 'gemini', label: 'Gemini 1.5', desc: 'Great for technical and coding topics' },
    { id: 'ollama', label: 'Ollama (local)', desc: 'Free, 100% private, no API key' },
  ];

  return (
    <div style={{ maxWidth: 640 }}>
      <div className="section-label">SETTINGS</div>
      <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 22, marginBottom: 28 }}>Preferences</h2>

      {/* Context prompt */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>Your context prompt</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>Tell the AI who you are and what the meeting is about. The more specific, the better the suggestions.</div>
        <textarea className="textarea-field" rows={5}
          placeholder={"Example: I'm interviewing for a Staff Engineer role at Acme Corp. My background is Python, distributed systems, and AWS. I have 8 years experience. Keep answers concise and confident."}
          value={s.contextPrompt}
          onChange={e => update({ contextPrompt: e.target.value })}
        />
      </div>

      {/* Model */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 12 }}>AI Model</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {MODELS.map(m => (
            <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 14, background: s.model === m.id ? 'var(--primary-10)' : 'var(--glass-bg)', border: `1px solid ${s.model === m.id ? 'var(--primary-30)' : 'var(--ghost-border)'}`, borderRadius: 'var(--radius-md)', padding: '12px 16px', cursor: 'pointer', transition: 'all 150ms' }}>
              <input type="radio" name="model" value={m.id} checked={s.model === m.id} onChange={() => update({ model: m.id })} style={{ accentColor: 'var(--primary-accent)' }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: s.model === m.id ? 'var(--primary)' : 'var(--text-primary)' }}>{m.label}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{m.desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* API Key */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>API Key</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>Optional — for Claude/GPT-4/Gemini. Stored locally, never sent to our servers.</div>
        <input className="form-input" type="password" placeholder="sk-ant-... or sk-..." value={s.apiKey} onChange={e => update({ apiKey: e.target.value })} />
      </div>

      {/* Silence threshold */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>
          Auto-trigger delay: <span style={{ color: 'var(--primary)' }}>{s.silenceMs}ms</span>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>How long to wait after they stop speaking before generating suggestions. Shorter = faster but may trigger mid-sentence.</div>
        <input type="range" min={800} max={4000} step={200} value={s.silenceMs} onChange={e => update({ silenceMs: Number(e.target.value) })} style={{ width: '100%', accentColor: 'var(--primary-accent)' }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-subtle)', marginTop: 4 }}>
          <span>800ms (fast)</span><span>2000ms (default)</span><span>4000ms (slow)</span>
        </div>
      </div>

      {/* Toggles */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 28 }}>
        {[
          { key: 'showTranscript' as const, label: 'Show live transcript', desc: 'Display the conversation as it happens' },
          { key: 'autoStart' as const, label: 'Auto-start listening', desc: 'Begin capturing audio as soon as meeting starts' },
        ].map(t => (
          <div key={t.key} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 0', borderBottom: '1px solid var(--ghost-border)' }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{t.label}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t.desc}</div>
            </div>
            <div className={`toggle-track ${s[t.key] ? 'toggle-on' : 'toggle-off'}`} onClick={() => update({ [t.key]: !s[t.key] })}>
              <div className="toggle-thumb" />
            </div>
          </div>
        ))}
      </div>

      <button className="btn-primary" onClick={() => showToast('✓ Settings saved')}>Save settings</button>
    </div>
  );
}

// ─── Documents / RAG Screen ───────────────────────────────────────────────────
function DocsScreen({ showToast }: { showToast: (m: string) => void }) {
  const [docs, setDocs] = useState<{ name: string; chunks: number; date: string }[]>(() => {
    try { return JSON.parse(localStorage.getItem('meetai_docs') ?? '[]'); } catch { return []; }
  });
  const [uploading, setUploading] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<string[]>([]);
  const [searching, setSearching] = useState(false);

  const handleFiles = async (files: FileList | null) => {
    if (!files) return;
    setUploading(true);
    const added = [];
    for (const file of Array.from(files)) {
      const { ok, chunks } = await uploadDocument(file);
      if (ok) {
        added.push({ name: file.name, chunks, date: new Date().toLocaleDateString() });
        showToast(`✓ Indexed ${file.name} (${chunks} chunks)`);
      } else {
        showToast(`⚠️ ${file.name} — start backend for RAG indexing`);
        added.push({ name: file.name, chunks: 0, date: new Date().toLocaleDateString() });
      }
    }
    const updated = [...added, ...docs];
    setDocs(updated);
    localStorage.setItem('meetai_docs', JSON.stringify(updated));
    setUploading(false);
  };

  const handleQuery = async () => {
    if (!query.trim()) return;
    setSearching(true);
    const { results: r } = await queryRAG(query);
    setResults(r);
    setSearching(false);
  };

  return (
    <div>
      <div className="section-label">DOCUMENTS</div>
      <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 22, marginBottom: 6 }}>Context documents</h2>
      <p style={{ fontSize: 14, color: 'var(--text-muted)', marginBottom: 28 }}>Upload your resume, company info, technical notes, or any docs. MeetAI uses these to ground AI answers in your real experience.</p>

      {/* Upload zone */}
      <label htmlFor="doc-upload" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, background: 'var(--glass-bg)', border: '2px dashed var(--ghost-border)', borderRadius: 'var(--radius-lg)', padding: '40px 24px', cursor: 'pointer', transition: 'border-color 200ms, background 200ms', marginBottom: 24 }}
        onDragOver={e => { e.preventDefault(); e.currentTarget.style.borderColor = 'var(--primary-accent)'; }}
        onDragLeave={e => { e.currentTarget.style.borderColor = 'var(--ghost-border)'; }}
        onDrop={e => { e.preventDefault(); handleFiles(e.dataTransfer.files); e.currentTarget.style.borderColor = 'var(--ghost-border)'; }}>
        <input id="doc-upload" type="file" multiple accept=".pdf,.docx,.txt,.md" style={{ display: 'none' }} onChange={e => handleFiles(e.target.files)} />
        <div style={{ fontSize: 36 }}>{uploading ? '⏳' : '📂'}</div>
        <div style={{ fontWeight: 600, fontSize: 14 }}>{uploading ? 'Indexing…' : 'Drop files here or click to upload'}</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>PDF, DOCX, TXT, Markdown · No size limit</div>
      </label>

      {/* Uploaded list */}
      {docs.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <div className="section-label">INDEXED DOCUMENTS</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {docs.map((d, i) => (
              <div key={i} className="glass-card" style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 14 }}>
                <span style={{ fontSize: 22 }}>{d.name.endsWith('.pdf') ? '📄' : d.name.endsWith('.docx') ? '📝' : '📃'}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{d.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{d.chunks > 0 ? `${d.chunks} chunks indexed` : 'Saved locally'} · {d.date}</div>
                </div>
                <div className="pill pill-success" style={{ fontSize: 10 }}>✓ Ready</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Query tester */}
      <div className="section-label">TEST RETRIEVAL</div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
        <input className="form-input" style={{ flex: 1 }} placeholder="e.g. What is my experience with microservices?" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleQuery()} />
        <button className="btn-primary" onClick={handleQuery} disabled={searching}>{searching ? '⏳' : '🔍 Search'}</button>
      </div>
      {results.map((r, i) => (
        <div key={i} className="glass-card" style={{ padding: '14px 16px', marginBottom: 8, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65 }}>{r}</div>
      ))}
    </div>
  );
}
