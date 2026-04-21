/**
 * MeetAI API Client  
 * ─────────────────────────────────────────────────────────────────────────────
 * • In Vite dev (port 5173)   → uses '' (empty base) so proxy forwards to 8765
 * • In Electron / production  → uses 'http://127.0.0.1:8765' directly
 * • Falls back to demo mode gracefully when offline
 */

// Detect environment: Electron sets window.ENV, Vite dev uses the proxy
const _electronBase: string | undefined = (window as any).ENV?.API_BASE;
const _isElectron = !!_electronBase;

// Vite dev  → BASE = '' (empty), so /health → Vite proxy → http://127.0.0.1:8765/health
// Electron  → BASE = explicit URL injected by the main process
// Production → BASE = explicit backend URL
export const BASE: string = _isElectron
  ? _electronBase!
  : (import.meta.env.DEV ? '' : 'http://127.0.0.1:8765');

// Shared fetch wrapper with timeout + JSON fallback
async function apiFetch(
  path: string,
  opts: RequestInit = {},
  timeoutMs = 6000,
): Promise<Response> {
  const url = `${BASE}${path}`;
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...opts, signal: controller.signal });
    return res;
  } finally {
    clearTimeout(id);
  }
}

// ─── Auth (localStorage-based, Supabase-ready) ─────────────────────────────

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  plan: 'free' | 'pro' | 'team';
  meetingsUsed: number;
  meetingsLimit: number;
}

export function getUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem('meetai_user');
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

export function saveUser(user: AuthUser) {
  localStorage.setItem('meetai_user', JSON.stringify(user));
}

export function signOut() {
  localStorage.removeItem('meetai_user');
}

export async function signIn(email: string, _password: string): Promise<AuthUser> {
  // Demo auth — swap with Supabase/Auth0 for production
  await new Promise(r => setTimeout(r, 700));
  const user: AuthUser = {
    id: btoa(email),
    email,
    name: email.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    plan: 'pro',
    meetingsUsed: 12,
    meetingsLimit: 100,
  };
  saveUser(user);
  return user;
}

export async function signUp(email: string, _password: string, name: string): Promise<AuthUser> {
  await new Promise(r => setTimeout(r, 900));
  const user: AuthUser = {
    id: btoa(email + Date.now()),
    email,
    name,
    plan: 'free',
    meetingsUsed: 0,
    meetingsLimit: 5,
  };
  saveUser(user);
  return user;
}

// ─── Health ─────────────────────────────────────────────────────────────────

export interface HealthStatus {
  online: boolean;
  whisper: boolean;
  llm: boolean;
  rag: boolean;
  model: string;
  engines?: {
    face?: { status: string; insightface: boolean; gfpgan: boolean };
    voice?: string;
    whisper?: boolean;
    rag?: boolean;
    llm?: boolean;
  };
}

export async function getHealth(): Promise<HealthStatus> {
  try {
    const res = await apiFetch('/health', {}, 3000);
    if (!res.ok) throw new Error('Non-200');
    const data = await res.json();
    return {
      online: true,
      whisper: data.engines?.whisper ?? false,
      llm: data.engines?.llm ?? false,
      rag: data.engines?.rag ?? false,
      model: data.engines?.llm ? 'connected' : 'demo',
      engines: data.engines,
    };
  } catch {
    return { online: false, whisper: false, llm: false, rag: false, model: 'demo' };
  }
}

// ─── Meeting lifecycle ───────────────────────────────────────────────────────

export interface MeetingSession {
  id: string;
  startedAt: number;
  status?: string;
}

export async function startMeeting(
  model: string,
  contextPrompt: string,
  jobTitle?: string,
  company?: string,
): Promise<MeetingSession> {
  try {
    const res = await apiFetch('/meeting/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        context: contextPrompt,
        job_title: jobTitle ?? '',
        company: company ?? '',
      }),
    });
    const data = await res.json();
    return { id: data.id ?? `mtg_${Date.now()}`, startedAt: Date.now(), status: data.status };
  } catch {
    return { id: `demo_${Date.now()}`, startedAt: Date.now() };
  }
}

export async function endMeeting(id: string): Promise<{ summary: string; actions: string[] }> {
  try {
    // The backend uses /meeting/end (session-scoped, not ID-scoped)
    const res = await apiFetch('/meeting/end', { method: 'POST' }, 15000);
    const data = await res.json();
    // Also trigger a summarize call
    try {
      const sumRes = await apiFetch('/meeting/summarize/rolling', { method: 'POST' }, 30000);
      const sumData = await sumRes.json();
      return { summary: sumData.notes ?? '', actions: [] };
    } catch {
      return { summary: data.summary ?? '', actions: [] };
    }
  } catch {
    return {
      summary: '## Meeting Summary\n\n_Backend unavailable — notes were not saved._',
      actions: [],
    };
  }
}

// ─── Suggestions ────────────────────────────────────────────────────────────

export interface Suggestion {
  type: 'answer' | 'detail' | 'followup' | 'clarify';
  text: string;
  confidence: number;
}

const DEMO_SUGGESTIONS: Record<string, Suggestion[]> = {
  default: [
    {
      type: 'answer', confidence: 92,
      text: "Great question. Based on my experience, I'd approach this by breaking it into smaller milestones — focusing first on the highest-value deliverable, then iterating based on real feedback rather than assumptions.",
    },
    {
      type: 'detail', confidence: 84,
      text: "To elaborate: the critical design decision is usually around data contracts and interface boundaries. Getting those right up front prevents 80% of the rework I've seen in large systems.",
    },
    {
      type: 'followup', confidence: 77,
      text: "That maps nicely to something I handled in my previous role — want me to walk through a concrete example with actual numbers?",
    },
  ],
};

export async function getSuggestions(
  question: string,
  _meetingId: string,
  model: string,
  contextPrompt?: string,
  jobTitle?: string,
  company?: string,
): Promise<Suggestion[]> {
  try {
    const res = await apiFetch('/meeting/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        model,
        context: contextPrompt ?? '',
        job_title: jobTitle ?? '',
        company: company ?? '',
        mode: 'auto',
      }),
    }, 12000);
    const data = await res.json();
    const raw = data.suggestions ?? [];
    if (raw.length === 0) return DEMO_SUGGESTIONS.default;

    // Normalize — backend may return {type, text, confidence} or just {label, text}
    return raw.map((s: any) => ({
      type: s.type ?? 'answer',
      text: s.text ?? s.answer ?? '',
      confidence: s.confidence ?? 85,
    })).filter((s: Suggestion) => s.text.length > 0);
  } catch {
    await new Promise(r => setTimeout(r, 300 + Math.random() * 400));
    return DEMO_SUGGESTIONS.default;
  }
}

// ─── Streaming suggestions (SSE) ────────────────────────────────────────────

export function streamSuggestion(
  question: string,
  _meetingId: string,
  model: string,
  onToken: (token: string) => void,
  onDone: () => void,
): () => void {
  // Backend SSE endpoint for streaming completions
  const url = `${BASE}/meeting/suggest/stream?question=${encodeURIComponent(question)}&model=${model}`;
  let es: EventSource | null = null;
  let closed = false;

  try {
    es = new EventSource(url);
    es.onmessage = (e) => {
      if (closed) return;
      try {
        const data = JSON.parse(e.data);
        if (data.done) { es?.close(); onDone(); return; }
        if (data.text) onToken(data.text);
        if (data.delta) onToken(data.delta);
      } catch {
        // Not JSON — raw token
        if (e.data !== '[DONE]') onToken(e.data);
        else { es?.close(); onDone(); }
      }
    };
    es.onerror = () => {
      if (!closed) { es?.close(); onDone(); }
    };
  } catch {
    // SSE not available — onDone immediately so getSuggestions runs
    onDone();
  }

  return () => {
    closed = true;
    es?.close();
  };
}

// ─── Transcript ──────────────────────────────────────────────────────────────

export async function pushTranscriptLine(
  _meetingId: string,
  speaker: 'You' | 'Them',
  text: string,
) {
  try {
    await apiFetch('/transcript/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ speaker, text }),
    }, 3000);
  } catch { /* transcript kept in UI state only when offline */ }
}

// ─── RAG ─────────────────────────────────────────────────────────────────────

export async function uploadDocument(file: File): Promise<{ ok: boolean; chunks: number }> {
  try {
    const fd = new FormData();
    fd.append('file', file);
    const res = await apiFetch('/rag/upload', { method: 'POST', body: fd }, 30000);
    if (!res.ok) throw new Error('upload failed');
    return await res.json();
  } catch {
    return { ok: false, chunks: 0 };
  }
}

export async function queryRAG(query: string): Promise<{ results: string[] }> {
  try {
    const res = await apiFetch('/rag/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    const data = await res.json();
    return { results: data.results ?? [] };
  } catch {
    return { results: ['RAG offline — start backend for document-grounded answers'] };
  }
}

// ─── Notes export ────────────────────────────────────────────────────────────

export async function exportNotesPDF(meetingId: string): Promise<boolean> {
  try {
    const res = await apiFetch(
      `/meeting/export?format=pdf&meeting_id=${meetingId}`, {}, 20000
    );
    if (!res.ok) throw new Error();
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `meetai-notes-${meetingId}.pdf`; a.click();
    URL.revokeObjectURL(url);
    return true;
  } catch { return false; }
}

export function exportNotesMD(notes: string, title = 'MeetAI Notes') {
  const blob = new Blob([`# ${title}\n\n${notes}`], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'meetai-notes.md'; a.click();
  URL.revokeObjectURL(url);
}

// ─── Past meetings ────────────────────────────────────────────────────────────

export interface PastMeeting {
  id: string;
  title: string;
  date: string;
  duration: string;
  model: string;
  suggestions: number;
  summary?: string;
}

const DEMO_MEETINGS: PastMeeting[] = [
  { id: 'd1', title: 'Staff Engineer Interview — Acme Corp', date: 'Today, 10:00 AM', duration: '42 min', model: 'Claude', suggestions: 18, summary: 'Discussed system design, distributed tracing, and team leadership at scale.' },
  { id: 'd2', title: 'Product Review — Q2 Roadmap', date: 'Yesterday', duration: '31 min', model: 'GPT-4', suggestions: 11, summary: 'Aligned on feature priorities and release timelines for Q2.' },
  { id: 'd3', title: 'Client Discovery Call', date: 'Mon Apr 13', duration: '58 min', model: 'Claude', suggestions: 24, summary: 'Explored pain points in their current CI/CD pipeline and negotiated next steps.' },
];

export function getPastMeetings(): PastMeeting[] {
  try {
    const raw = localStorage.getItem('meetai_meetings');
    return raw ? JSON.parse(raw) : DEMO_MEETINGS;
  } catch { return DEMO_MEETINGS; }
}

export function saveMeeting(m: PastMeeting) {
  const all = getPastMeetings().filter(x => x.id !== m.id);
  localStorage.setItem('meetai_meetings', JSON.stringify([m, ...all].slice(0, 50)));
}

// ─── Settings ────────────────────────────────────────────────────────────────

export interface AppSettings {
  model: string;
  contextPrompt: string;
  jobTitle: string;
  company: string;
  silenceMs: number;
  autoStart: boolean;
  apiKey: string;
  showTranscript: boolean;
}

const DEFAULT_SETTINGS: AppSettings = {
  model: 'ollama',
  contextPrompt: '',
  jobTitle: '',
  company: '',
  silenceMs: 1800,
  autoStart: true,
  apiKey: '',
  showTranscript: true,
};

export function getSettings(): AppSettings {
  try {
    const raw = localStorage.getItem('meetai_settings');
    return raw ? { ...DEFAULT_SETTINGS, ...JSON.parse(raw) } : DEFAULT_SETTINGS;
  } catch { return DEFAULT_SETTINGS; }
}

export function saveSettings(s: Partial<AppSettings>) {
  const current = getSettings();
  localStorage.setItem('meetai_settings', JSON.stringify({ ...current, ...s }));
}

// ─── Voice Cloning ───────────────────────────────────────────────────────────

export interface VoiceProfile {
  id: string;
  name: string;
  created_at: string;
}

export async function uploadVoiceProfile(name: string, file: File): Promise<VoiceProfile | null> {
  try {
    const fd = new FormData();
    fd.append('name', name);
    fd.append('file', file);
    const res = await apiFetch('/voice/upload', { method: 'POST', body: fd }, 30000);
    if (!res.ok) throw new Error();
    return await res.json();
  } catch { return null; }
}

export async function listVoiceProfiles(): Promise<VoiceProfile[]> {
  try {
    const res = await apiFetch('/voice/profiles', {}, 5000);
    if (!res.ok) throw new Error();
    return await res.json();
  } catch { return []; }
}

export async function synthesizeVoice(text: string, profileId: string): Promise<boolean> {
  try {
    const res = await apiFetch('/voice/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, profile_id: profileId }),
    });
    return res.ok;
  } catch { return false; }
}
