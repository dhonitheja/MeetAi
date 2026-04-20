import { useState, useEffect, useRef, useCallback } from 'react';
import type { AIModel, Screen, TranscriptLine } from './data';
import {
  MOCK_TRANSCRIPT, MOCK_SUGGESTIONS, MOCK_NOTES, MOCK_MEETINGS, MOCK_DOCUMENTS, MODEL_LABELS,
} from './data';
import {
  getHealth, startMeeting, endMeeting, askQuestion, streamSuggestion,
  addTranscriptLine, getLiveTranscript, summarizeMeeting, uploadDocument, exportNotes,
} from './api';
import type { HealthStatus, Suggestion as APISuggestion } from './api';

// ─── BackendBadge ────────────────────────────────────────────────────────────

function BackendBadge({ health }: { health: HealthStatus | null }) {
  if (!health) return null;
  const online = health.status === 'ok';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10, color: online ? 'var(--success)' : '#64748b' }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: online ? 'var(--success)' : '#475569', flexShrink: 0, display: 'inline-block' }} />
      {online
        ? `Backend · Whisper ${health.whisper ? '✓' : '✗'} · RAG ${health.rag_chunks}chunks · LLM ${health.llm ? '✓' : '✗'}`
        : 'Backend offline — demo mode'}
    </div>
  );
}

// ─── Home Screen ─────────────────────────────────────────────────────────────

interface HomeScreenProps {
  selectedModel: AIModel;
  setSelectedModel: (m: AIModel) => void;
  setScreen: (s: Screen) => void;
}

export function HomeScreen({ selectedModel, setSelectedModel, setScreen }: HomeScreenProps) {
  const [health, setHealth] = useState<HealthStatus | null>(null);

  useEffect(() => {
    getHealth().then(setHealth);
    const id = setInterval(() => getHealth().then(setHealth), 8000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="screen">
      {/* Logo */}
      <div style={{ textAlign: 'center', padding: '14px 0 18px' }}>
        <div style={{ fontSize: 36, color: 'var(--primary)', marginBottom: 6, lineHeight: 1 }}>◈</div>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 800, letterSpacing: 8, color: '#fff', marginBottom: 4 }}>
          MEETAI
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', letterSpacing: 1, marginBottom: 8 }}>
          Your invisible AI meeting copilot
        </div>
        <BackendBadge health={health} />
      </div>

      {/* Status */}
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 24 }}>
        <div className={`pill ${health?.status === 'ok' ? 'pill-success' : 'pill-primary'}`}>
          <span className={`dot ${health?.status === 'ok' ? 'dot-success' : 'dot-live'}`} />
          {health?.status === 'ok' ? `Ready · ${MODEL_LABELS[selectedModel]} active` : `${MODEL_LABELS[selectedModel]} · Demo mode`}
        </div>
      </div>

      {/* Action Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 22 }}>
        <ActionCard icon="🎙️" label="Start Meeting" sub="Listen & assist live" color="#6366f1" onClick={() => setScreen('meeting')} />
        <ActionCard icon="⚙️" label="Setup" sub="Prompt + docs" color="#8b5cf6" onClick={() => setScreen('setup')} />
        <ActionCard icon="📋" label="Notes" sub="Past meetings" color="#0ea5e9" onClick={() => setScreen('notes')} />
        <ActionCard icon="📁" label="Documents" sub="Your context files" color="#10b981" onClick={() => setScreen('docs')} />
      </div>

      {/* Model Selector */}
      <div style={{ marginBottom: 22 }}>
        <div className="section-label" style={{ marginTop: 0 }}>AI Model</div>
        <div className="model-tabs">
          {(['claude', 'gpt4', 'gemini', 'ollama'] as AIModel[]).map((k) => (
            <button key={k} className={`model-tab ${selectedModel === k ? 'active' : ''}`} onClick={() => setSelectedModel(k)}>
              {MODEL_LABELS[k]}
            </button>
          ))}
        </div>
      </div>

      {/* Stealth status card */}
      <div className="glass-card" style={{ padding: '10px 14px', marginBottom: 22, display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ width: 34, height: 34, borderRadius: 8, background: 'rgba(99,102,241,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, flexShrink: 0 }}>🛡️</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>Stealth Mode</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>WDA_EXCLUDEFROMCAPTURE active on Windows</div>
        </div>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--success)', flexShrink: 0 }} />
      </div>

      {/* Recent Meetings */}
      <div className="section-label" style={{ marginTop: 0 }}>Recent Meetings</div>
      {MOCK_MEETINGS.map((m) => (
        <div key={m.id} className="glass-card interactive hover-lift" onClick={() => setScreen('notes')}
          style={{ padding: '12px 14px', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 34, height: 34, borderRadius: 8, background: 'var(--primary-10)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, flexShrink: 0 }}>
            {m.model === 'claude' ? '🤖' : m.model === 'gpt4' ? '✨' : '⭐'}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>{m.title}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{m.date} · {m.duration} · {MODEL_LABELS[m.model]}</div>
          </div>
          <div style={{ color: 'var(--text-subtle)', fontSize: 20, lineHeight: 1 }}>›</div>
        </div>
      ))}
    </div>
  );
}

// ─── ActionCard ───────────────────────────────────────────────────────────────

function ActionCard({ icon, label, sub, color, onClick }: { icon: string; label: string; sub: string; color: string; onClick: () => void }) {
  const [hover, setHover] = useState(false);
  return (
    <div
      className="glass-card interactive"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        padding: '14px 12px',
        transform: hover ? 'scale(0.975)' : 'scale(1)',
        transition: 'transform 0.15s var(--ease-out), border-color 0.15s var(--ease-out)',
        borderColor: hover ? `${color}40` : undefined,
      }}
    >
      <div style={{ width: 38, height: 38, borderRadius: 10, background: `${color}1a`, color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, marginBottom: 9 }}>
        {icon}
      </div>
      <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{sub}</div>
    </div>
  );
}

// ─── Setup Screen ─────────────────────────────────────────────────────────────

interface SetupScreenProps { setScreen: (s: Screen) => void; }

export function SetupScreen({ setScreen }: SetupScreenProps) {
  const [prompt, setPrompt] = useState("I'm interviewing at Acme Corp for a Staff Engineer role. Focus on system design, distributed systems, and cloud architecture. Help me give concise, technical answers.");
  const [saved, setSaved] = useState(true);
  const [stealthOn, setStealthOn] = useState(true);
  const [docs, setDocs] = useState(MOCK_DOCUMENTS);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Persist prompt in localStorage for Meeting screen to pick up
  useEffect(() => {
    const stored = localStorage.getItem('meetai_prompt');
    if (stored) setPrompt(stored);
  }, []);

  const savePrompt = () => {
    localStorage.setItem('meetai_prompt', prompt);
    setSaved(true);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMsg('Uploading…');
    const result = await uploadDocument(file);
    if (result) {
      setDocs(prev => [...prev, {
        id: Date.now().toString(),
        name: file.name,
        size: `${(file.size / 1024).toFixed(0)} KB`,
        status: 'indexed',
        chunks: result.chunks,
      }]);
      setUploadMsg(`✓ Indexed ${result.chunks} chunks`);
    } else {
      // Offline: add locally with processing status
      setDocs(prev => [...prev, {
        id: Date.now().toString(),
        name: file.name,
        size: `${(file.size / 1024).toFixed(0)} KB`,
        status: 'indexed',
        chunks: Math.floor(Math.random() * 60) + 20,
      }]);
      setUploadMsg('Saved locally (demo mode)');
    }
    setUploading(false);
    setTimeout(() => setUploadMsg(''), 3000);
    e.target.value = '';
  };

  return (
    <div className="screen">
      <div className="nav-header">
        <button className="nav-back-btn" onClick={() => setScreen('home')}>‹</button>
        <h1 className="nav-title">Meeting Setup</h1>
      </div>

      <div className="section-label" style={{ marginTop: 0 }}>Context Prompt</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>
        Tell the AI your role, meeting type, and goals for tailored suggestions
      </div>
      <textarea
        className="textarea-field"
        rows={5}
        value={prompt}
        onChange={(e) => { setPrompt(e.target.value); setSaved(false); }}
        placeholder="e.g. I'm a senior engineer interviewing at Acme Corp…"
      />
      <button className="btn-ghost" style={{ marginTop: 8, alignSelf: 'flex-start' }} onClick={savePrompt}>
        {saved ? '✓ Saved' : 'Save Prompt'}
      </button>

      <div className="section-label">Documents (RAG Context)</div>
      <div
        className="glass-card"
        style={{ border: '1.5px dashed rgba(99,102,241,0.35)', textAlign: 'center', padding: '20px 14px', marginBottom: 12, cursor: 'pointer', opacity: uploading ? 0.6 : 1 }}
        onClick={() => !uploading && fileInputRef.current?.click()}
      >
        <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt,.md" style={{ display: 'none' }} onChange={handleFileUpload} />
        <div style={{ fontSize: 22, marginBottom: 6 }}>{uploading ? '⏳' : '📎'}</div>
        <div style={{ fontSize: 14, color: 'var(--primary)', fontWeight: 500 }}>
          {uploading ? 'Indexing…' : uploadMsg || 'Add files for context'}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>PDF, DOCX, TXT · used for RAG retrieval</div>
      </div>
      {docs.map((doc) => (
        <div key={doc.id} className="glass-card" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 13px', marginBottom: 7 }}>
          <span style={{ fontSize: 18 }}>📄</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{doc.name}</div>
            <div style={{ fontSize: 11, color: doc.status === 'indexed' ? 'var(--success)' : 'var(--warning)', marginTop: 1 }}>
              {doc.status === 'indexed' ? `✓ Indexed · ${doc.chunks} chunks` : 'Processing…'}
            </div>
          </div>
          <button style={{ color: 'var(--text-subtle)', fontSize: 14, padding: 4 }}
            onClick={() => setDocs(docs.filter(d => d.id !== doc.id))}>✕</button>
        </div>
      ))}

      <div className="section-label">Stealth Mode</div>
      <div className="glass-card" style={{ padding: '13px 15px', display: 'flex', alignItems: 'center', gap: 12, justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>Hide from screen capture</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>
            Windows: WDA_EXCLUDEFROMCAPTURE · macOS: NSWindow.sharingType
          </div>
        </div>
        <div className={`toggle-track ${stealthOn ? 'toggle-on' : 'toggle-off'}`} onClick={() => setStealthOn(!stealthOn)}>
          <div className="toggle-thumb" />
        </div>
      </div>

      <button className="btn-primary" style={{ marginTop: 24 }} onClick={() => setScreen('meeting')}>
        Start Meeting →
      </button>
    </div>
  );
}

// ─── Meeting Screen ───────────────────────────────────────────────────────────

interface MeetingScreenProps { selectedModel: AIModel; setScreen: (s: Screen) => void; }

export function MeetingScreen({ selectedModel, setScreen }: MeetingScreenProps) {
  const [isListening, setIsListening] = useState(false);
  const [activeSuggestion, setActiveSuggestion] = useState<number | null>(0);
  const [minimized, setMinimized] = useState(false);
  const [showCopied, setShowCopied] = useState(false);
  const [audioLevels, setAudioLevels] = useState<number[]>(Array(24).fill(4));
  const [elapsed, setElapsed] = useState(0);

  // Live state
  const [transcript, setTranscript] = useState<TranscriptLine[]>(MOCK_TRANSCRIPT);
  const [suggestions, setSuggestions] = useState(MOCK_SUGGESTIONS.map((s, i) => ({ ...s, id: i })));
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [questionInput, setQuestionInput] = useState('');
  const [meetingStarted, setMeetingStarted] = useState(false);
  const [backendOnline, setBackendOnline] = useState(false);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const streamCleanupRef = useRef<(() => void) | null>(null);

  // Start meeting on mount
  useEffect(() => {
    const ctx = localStorage.getItem('meetai_prompt') || '';
    startMeeting(selectedModel, ctx).then(ok => setBackendOnline(ok));

    timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000);

    // Poll live transcript every 3s
    pollRef.current = setInterval(async () => {
      const data = await getLiveTranscript();
      if (data.lines.length > 0) {
        setTranscript(data.lines.map((l, i) => ({
          id: i, speaker: l.speaker as 'You' | 'Them', text: l.text, time: l.time,
        })));
      }
    }, 3000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (pollRef.current) clearInterval(pollRef.current);
      if (audioRef.current) clearInterval(audioRef.current);
      if (streamCleanupRef.current) streamCleanupRef.current();
    };
  }, [selectedModel]);

  // Audio viz
  useEffect(() => {
    if (isListening) {
      audioRef.current = setInterval(() => {
        setAudioLevels(Array.from({ length: 24 }, (_, i) =>
          4 + Math.abs(Math.sin(Date.now() / 200 + i * 0.6)) * 32 + Math.random() * 8
        ));
      }, 80);
    } else {
      if (audioRef.current) clearInterval(audioRef.current);
      setAudioLevels(Array(24).fill(4));
    }
  }, [isListening]);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript]);

  const formatTime = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  const copyText = useCallback((text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setShowCopied(true);
    setTimeout(() => setShowCopied(false), 1600);
  }, []);

  // Fetch AI suggestions for a question (with SSE streaming fallback)
  const fetchSuggestions = useCallback(async (question: string) => {
    if (!question.trim()) return;
    setLoadingSuggestions(true);
    setSuggestions([]);
    setStreamingText('');

    // Add to transcript
    const newLine: TranscriptLine = { id: Date.now(), speaker: 'Them', text: question, time: new Date().toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' }) };
    setTranscript(prev => [...prev, newLine]);
    await addTranscriptLine('Them', question);

    if (backendOnline) {
      // Use streaming for the first card, batch for the rest
      let streamBuffer = '';
      if (streamCleanupRef.current) streamCleanupRef.current();
      streamCleanupRef.current = streamSuggestion(
        question, selectedModel,
        (token) => { streamBuffer += token; setStreamingText(streamBuffer); },
        async () => {
          setStreamingText('');
          // Now fetch full structured suggestions
          const results = await askQuestion(question);
          if (results.length > 0) {
            setSuggestions(results.map((s, i) => ({ ...s, id: i })));
          } else {
            setSuggestions(MOCK_SUGGESTIONS.map((s, i) => ({ ...s, id: i })));
          }
          setLoadingSuggestions(false);
          setActiveSuggestion(0);
        }
      );
    } else {
      // Demo mode: shuffle mock suggestions
      await new Promise(r => setTimeout(r, 900));
      setSuggestions(MOCK_SUGGESTIONS.map((s, i) => ({ ...s, id: i, confidence: s.confidence - Math.floor(Math.random() * 8) })));
      setLoadingSuggestions(false);
      setActiveSuggestion(0);
    }
  }, [backendOnline, selectedModel]);

  const handleEnd = async () => {
    if (timerRef.current) clearInterval(timerRef.current);
    await endMeeting();
    const notes = await summarizeMeeting(transcript.map(l => ({ speaker: l.speaker, text: l.text })));
    if (notes) localStorage.setItem('meetai_notes', notes);
    setScreen('notes');
  };

  return (
    <div className="screen">
      {/* Live Bar */}
      <div className="glass-card pill-live" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 13px', marginBottom: 14, borderRadius: 10, border: '1px solid var(--live-20)' }}>
        <span className="dot dot-live" />
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 2, color: 'var(--live)' }}>LIVE</span>
        <span style={{ flex: 1, fontSize: 13, color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>{formatTime(elapsed)}</span>
        <span style={{ fontSize: 10, color: backendOnline ? 'var(--success)' : '#64748b', marginRight: 4 }}>
          {backendOnline ? '● API' : '○ Demo'}
        </span>
        <button style={{ background: 'var(--glass-bg)', border: '1px solid var(--ghost-border)', borderRadius: 6, color: 'var(--text-muted)', padding: '4px 8px', fontSize: 11 }} onClick={() => setMinimized(!minimized)}>
          {minimized ? '▲ Expand' : '▼ Min'}
        </button>
        <button style={{ background: 'var(--live-10)', border: '1px solid var(--live-20)', borderRadius: 6, color: '#f87171', padding: '4px 10px', fontSize: 12 }}
          onClick={handleEnd}>
          End
        </button>
      </div>

      {minimized ? (
        <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 20px', cursor: 'pointer', gap: 10 }}
          onClick={() => setMinimized(false)}>
          <div style={{ fontSize: 40, color: 'var(--primary)', animation: 'pulse-dot 2s ease-in-out infinite' }}>◈</div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>MeetAI running · tap to expand</div>
        </div>
      ) : (
        <>
          {/* Audio Viz + mic button */}
          <div className="glass-card" style={{ padding: '14px 14px', marginBottom: 14, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
            <button
              onClick={() => setIsListening(!isListening)}
              style={{ width: 50, height: 50, borderRadius: '50%', fontSize: 22, background: isListening ? 'rgba(99,102,241,0.2)' : 'var(--glass-bg)', border: `2px solid ${isListening ? 'rgba(99,102,241,0.6)' : 'var(--ghost-border)'}`, transition: 'all 0.2s' }}
            >
              {isListening ? '🎙️' : '🎤'}
            </button>
            <div style={{ display: 'flex', gap: 3, alignItems: 'flex-end', height: 44 }}>
              {audioLevels.map((h, i) => (
                <div key={i} className="audio-bar" style={{ height: h, background: isListening ? `hsl(${235 + i * 3}, 80%, ${55 + i % 4 * 5}%)` : undefined }} />
              ))}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              {isListening ? 'Listening & transcribing…' : 'Tap microphone to start listening'}
            </div>
          </div>

          {/* Ask box — type a question to get suggestions */}
          <div className="glass-card" style={{ padding: '10px 12px', marginBottom: 12, display: 'flex', gap: 8 }}>
            <input
              type="text"
              value={questionInput}
              onChange={e => setQuestionInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { fetchSuggestions(questionInput); setQuestionInput(''); } }}
              placeholder='Type their question → press Enter for AI suggestions…'
              style={{
                flex: 1, background: 'transparent', border: 'none', outline: 'none',
                fontSize: 12, color: 'var(--text-primary)', fontFamily: 'var(--font-body)',
              }}
            />
            <button
              onClick={() => { fetchSuggestions(questionInput); setQuestionInput(''); }}
              style={{ fontSize: 16, color: 'var(--primary)', padding: '0 4px', opacity: questionInput ? 1 : 0.3 }}
            >⤵</button>
          </div>

          {/* Transcript */}
          <div className="glass-card" style={{ padding: '12px 13px', marginBottom: 14 }}>
            <div className="section-label" style={{ marginTop: 0, marginBottom: 10 }}>Live Transcript</div>
            <div style={{ maxHeight: 180, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {transcript.map((t) => (
                <TranscriptLineItem key={t.id} line={t} />
              ))}
              <div style={{ paddingLeft: 12, borderLeft: '2px solid var(--warning)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-subtle)', marginBottom: 3 }}>Them · now</div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)', fontStyle: 'italic', display: 'flex', alignItems: 'center', gap: 0 }}>
                  <span className="cursor-blink" />speaking…
                </div>
              </div>
              <div ref={transcriptEndRef} />
            </div>
          </div>

          {/* Suggestions */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
              {loadingSuggestions ? 'Thinking…' : 'AI Suggestions'}
            </div>
            <span className="pill pill-primary" style={{ fontSize: 10, padding: '3px 9px' }}>{MODEL_LABELS[selectedModel]}</span>
          </div>

          {/* SSE streaming card */}
          {streamingText && (
            <div className="glass-card" style={{ padding: '12px 13px', marginBottom: 8, borderColor: 'rgba(99,102,241,0.35)', background: 'rgba(99,102,241,0.05)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 16 }}>✨</span>
                <span style={{ flex: 1, fontSize: 13, fontWeight: 500, color: 'var(--primary)' }}>Streaming…</span>
                <span className="cursor-blink" />
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.65 }}>{streamingText}</div>
            </div>
          )}

          {loadingSuggestions && !streamingText && (
            <div className="glass-card" style={{ padding: '24px', textAlign: 'center' }}>
              <div style={{ fontSize: 24, marginBottom: 8, animation: 'pulse-dot 1.5s ease infinite' }}>◈</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Generating suggestions…</div>
            </div>
          )}

          {!loadingSuggestions && suggestions.map((s, i) => (
            <SuggestionCard key={i} suggestion={s} isOpen={activeSuggestion === i}
              onToggle={() => setActiveSuggestion(activeSuggestion === i ? null : i)}
              onCopy={copyText} />
          ))}

          {/* Quick-fire question chips */}
          {!loadingSuggestions && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4, paddingBottom: 8 }}>
              {[
                'Tell me about yourself',
                'System design approach?',
                'Biggest technical challenge?',
                'How do you handle conflict?',
              ].map((q) => (
                <button key={q}
                  onClick={() => fetchSuggestions(q)}
                  style={{ fontSize: 10, padding: '4px 9px', borderRadius: 12, background: 'var(--glass-bg)', border: '1px solid var(--ghost-border)', color: 'var(--text-muted)', cursor: 'pointer', transition: 'all 0.15s' }}
                  onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(99,102,241,0.4)')}
                  onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--ghost-border)')}
                >{q}</button>
              ))}
            </div>
          )}
        </>
      )}

      {showCopied && <div className="toast">Copied to clipboard ✓</div>}
    </div>
  );
}

function TranscriptLineItem({ line }: { line: TranscriptLine }) {
  const isYou = line.speaker === 'You';
  return (
    <div style={{ paddingLeft: 12, borderLeft: `2px solid ${isYou ? 'var(--success)' : 'var(--primary-accent)'}` }}>
      <div style={{ fontSize: 10, color: 'var(--text-subtle)', marginBottom: 3 }}>{line.speaker} · {line.time}</div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{line.text}</div>
    </div>
  );
}

function SuggestionCard({ suggestion, isOpen, onToggle, onCopy }: {
  suggestion: { id: number; icon: string; label: string; confidence: number; text: string };
  isOpen: boolean;
  onToggle: () => void;
  onCopy: (text: string) => void;
}) {
  return (
    <div className="glass-card" onClick={onToggle} style={{ padding: '12px 13px', marginBottom: 8, cursor: 'pointer', borderColor: isOpen ? 'rgba(99,102,241,0.35)' : undefined, background: isOpen ? 'rgba(99,102,241,0.05)' : undefined, transition: 'all 0.2s' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 16 }}>{suggestion.icon}</span>
        <span style={{ flex: 1, fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{suggestion.label}</span>
        <span style={{ fontSize: 10, color: 'var(--success)', background: 'var(--success-10)', borderRadius: 4, padding: '2px 6px' }}>{suggestion.confidence}%</span>
        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{isOpen ? '▲' : '▼'}</span>
      </div>
      {isOpen && (
        <>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.65, marginTop: 11, paddingTop: 11, borderTop: '1px solid var(--outline-variant)' }}>
            {suggestion.text}
          </div>
          <button className="btn-ghost" style={{ marginTop: 10, fontSize: 12 }} onClick={(e) => { e.stopPropagation(); onCopy(suggestion.text); }}>
            Copy ↗
          </button>
        </>
      )}
    </div>
  );
}

// ─── Notes Screen ─────────────────────────────────────────────────────────────

interface NotesScreenProps { setScreen: (s: Screen) => void; }

export function NotesScreen({ setScreen }: NotesScreenProps) {
  const [exported, setExported] = useState('');
  const [exporting, setExporting] = useState(false);

  // Prefer LLM-generated notes saved from meeting, fall back to mock
  const notes = localStorage.getItem('meetai_notes') || MOCK_NOTES;

  const handleExport = async (format: 'md' | 'pdf' | 'docx') => {
    setExporting(true);
    // Try backend export first
    const ok = await exportNotes(format);
    if (!ok) {
      // Fallback: client-side MD export
      const blob = new Blob([notes], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `meeting-notes.${format}`; a.click();
      URL.revokeObjectURL(url);
    }
    setExported(format.toUpperCase());
    setExporting(false);
    setTimeout(() => setExported(''), 2000);
  };

  return (
    <div className="screen">
      <div className="nav-header">
        <button className="nav-back-btn" onClick={() => setScreen('home')}>‹</button>
        <h1 className="nav-title">Meeting Notes</h1>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
        </span>
        <span className="pill pill-primary" style={{ fontSize: 10, padding: '2px 8px' }}>Claude</span>
        {localStorage.getItem('meetai_notes') && (
          <span style={{ fontSize: 10, color: 'var(--success)', padding: '2px 8px', background: 'var(--success-10)', borderRadius: 6 }}>● Live summary</span>
        )}
      </div>

      <div className="glass-card" style={{ padding: '14px 16px', marginBottom: 18 }}>
        <NotesRenderer markdown={notes} />
      </div>

      {/* Export */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Export as</div>
        <div style={{ display: 'flex', gap: 6 }}>
          {(['md', 'pdf', 'docx'] as const).map((f) => (
            <button key={f} className="btn-ghost"
              style={{ padding: '6px 14px', fontSize: 12, textTransform: 'uppercase', opacity: exporting ? 0.5 : 1 }}
              onClick={() => !exporting && handleExport(f)}>
              {f}
            </button>
          ))}
        </div>
      </div>

      {exported && <div className="toast">Exported as {exported} ✓</div>}
    </div>
  );
}

function NotesRenderer({ markdown }: { markdown: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {markdown.split('\n').map((line, i) => {
        if (line.startsWith('## ')) return <div key={i} style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 700, color: '#fff', marginBottom: 6, marginTop: 4 }}>{line.slice(3)}</div>;
        if (line.startsWith('### ')) return <div key={i} style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--primary)', letterSpacing: 0.3, marginTop: 12, marginBottom: 5 }}>{line.slice(4)}</div>;
        if (line.startsWith('- [ ]')) return <div key={i} style={{ fontSize: 13, color: 'var(--warning)', lineHeight: 1.8, paddingLeft: 4 }}>☐ {line.slice(6)}</div>;
        if (line.startsWith('- [x]')) return <div key={i} style={{ fontSize: 13, color: 'var(--success)', lineHeight: 1.8, paddingLeft: 4 }}>☑ {line.slice(6)}</div>;
        if (line.startsWith('- ')) return <div key={i} style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8, paddingLeft: 4 }}>• {line.slice(2)}</div>;
        if (line.trim()) return <div key={i} style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6 }}>{line}</div>;
        return <div key={i} style={{ height: 4 }} />;
      })}
    </div>
  );
}

// ─── Documents Screen ─────────────────────────────────────────────────────────

interface DocsScreenProps { setScreen: (s: Screen) => void; }

export function DocsScreen({ setScreen }: DocsScreenProps) {
  const [docs, setDocs] = useState(MOCK_DOCUMENTS);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const [query, setQuery] = useState('');
  const [ragResults, setRagResults] = useState<string[]>([]);
  const [querying, setQuerying] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const result = await uploadDocument(file);
    const newDoc = {
      id: Date.now().toString(),
      name: file.name,
      size: `${(file.size / 1024).toFixed(0)} KB`,
      status: 'indexed' as const,
      chunks: result?.chunks ?? Math.floor(Math.random() * 60) + 20,
    };
    setDocs(prev => [...prev, newDoc]);
    setUploadMsg(result ? `✓ Indexed ${result.chunks} chunks` : 'Saved locally');
    setUploading(false);
    setTimeout(() => setUploadMsg(''), 3000);
    e.target.value = '';
  };

  const handleQuery = async () => {
    if (!query.trim()) return;
    setQuerying(true);
    setRagResults([]);
    try {
      const res = await fetch(`http://localhost:8765/rag/query?q=${encodeURIComponent(query)}&n=3`, { signal: AbortSignal.timeout(8000) });
      const data = await res.json();
      setRagResults(data.results ?? []);
    } catch {
      setRagResults(['Backend offline — RAG query not available in demo mode.']);
    }
    setQuerying(false);
  };

  const totalChunks = docs.filter(d => d.status === 'indexed').reduce((a, d) => a + (d.chunks || 0), 0);

  return (
    <div className="screen">
      <div className="nav-header">
        <button className="nav-back-btn" onClick={() => setScreen('home')}>‹</button>
        <h1 className="nav-title">Documents</h1>
      </div>

      {/* RAG Status */}
      <div className="glass-card" style={{ padding: '12px 14px', marginBottom: 16, display: 'flex', gap: 10, alignItems: 'center' }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, color: 'var(--success)', fontWeight: 500 }}>● Vector store ready</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
            {docs.filter(d => d.status === 'indexed').length} docs · {totalChunks} chunks indexed
          </div>
        </div>
        <div style={{ fontSize: 10, color: 'var(--primary)', background: 'var(--primary-10)', borderRadius: 6, padding: '4px 8px' }}>
          MiniLM-L6
        </div>
      </div>

      {/* Upload area */}
      <div className="glass-card"
        style={{ border: '1.5px dashed rgba(99,102,241,0.35)', textAlign: 'center', padding: '18px 14px', marginBottom: 14, cursor: 'pointer', opacity: uploading ? 0.6 : 1 }}
        onClick={() => !uploading && fileInputRef.current?.click()}>
        <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt,.md" style={{ display: 'none' }} onChange={handleFileUpload} />
        <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'var(--primary-10)', border: '1px solid var(--primary-30)', color: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, margin: '0 auto 8px' }}>
          {uploading ? '⏳' : '+'}
        </div>
        <div style={{ fontSize: 14, color: 'var(--primary)', fontWeight: 500 }}>
          {uploadMsg || (uploading ? 'Indexing…' : 'Add Document')}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>PDF, DOCX, TXT, Markdown — for RAG retrieval</div>
      </div>

      {/* RAG query tester */}
      <div className="glass-card" style={{ padding: '10px 12px', marginBottom: 14, display: 'flex', gap: 8 }}>
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleQuery()}
          placeholder="Test RAG query…"
          style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontSize: 12, color: 'var(--text-primary)', fontFamily: 'var(--font-body)' }}
        />
        <button onClick={handleQuery} style={{ fontSize: 14, color: 'var(--primary)', padding: '0 4px', opacity: query ? 1 : 0.3 }}>⤵</button>
      </div>
      {querying && <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10, paddingLeft: 4 }}>Searching vectors…</div>}
      {ragResults.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          {ragResults.map((r, i) => (
            <div key={i} className="glass-card" style={{ padding: '10px 12px', marginBottom: 6, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5, borderColor: 'rgba(16,185,129,0.2)' }}>
              <span style={{ color: 'var(--success)', fontWeight: 600, marginRight: 6 }}>#{i + 1}</span>{r.slice(0, 300)}{r.length > 300 ? '…' : ''}
            </div>
          ))}
        </div>
      )}

      {/* Document list */}
      <div className="section-label" style={{ marginTop: 0 }}>Context Documents</div>
      {docs.map((doc) => (
        <div key={doc.id} className="glass-card" style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', marginBottom: 8 }}>
          <div style={{ fontSize: 28, flexShrink: 0 }}>📄</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>{doc.name}</div>
            <div style={{ fontSize: 11 }}>
              <span style={{ color: 'var(--text-muted)' }}>{doc.size} · </span>
              {doc.status === 'indexed'
                ? <span style={{ color: 'var(--success)' }}>✓ Indexed · {doc.chunks} chunks</span>
                : <span className="shimmer" style={{ color: 'var(--warning)' }}>Processing…</span>
              }
            </div>
          </div>
          <button style={{ color: 'var(--text-subtle)', fontSize: 16, padding: 4, flexShrink: 0 }}
            onClick={() => setDocs(docs.filter((d) => d.id !== doc.id))}>
            ✕
          </button>
        </div>
      ))}

      {/* Coverage visualization */}
      <div className="section-label">Context Coverage</div>
      <div className="glass-card" style={{ padding: '14px' }}>
        {[
          { label: 'Technical Skills', pct: 92, color: '#6366f1' },
          { label: 'Company Research', pct: 60, color: '#8b5cf6' },
          { label: 'System Design', pct: 85, color: '#10b981' },
          { label: 'Behavioral', pct: 40, color: '#0ea5e9' },
        ].map((item) => (
          <div key={item.label} style={{ marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 5 }}>
              <span>{item.label}</span>
              <span style={{ color: item.color }}>{item.pct}%</span>
            </div>
            <div style={{ height: 4, background: 'var(--surface-highest)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${item.pct}%`, background: item.color, borderRadius: 2, transition: 'width 0.6s var(--ease-out)' }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
