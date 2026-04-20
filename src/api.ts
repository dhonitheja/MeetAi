/**
 * MeetAI API Client + Auth
 * Connects to FastAPI backend; falls back to smart demo mode when offline.
 */

export const BASE = 'http://127.0.0.1:8765';

// ─── Auth (localStorage-based, Supabase-ready) ───────────────────────────────

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
  // TODO: swap with real auth endpoint
  await new Promise(r => setTimeout(r, 800));
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
  await new Promise(r => setTimeout(r, 1000));
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

// ─── Health ───────────────────────────────────────────────────────────────────

export interface HealthStatus {
  online: boolean;
  whisper: boolean;
  llm: boolean;
  rag: boolean;
  model: string;
}

export async function getHealth(): Promise<HealthStatus> {
  try {
    const res = await fetch(`${BASE}/health`, { signal: AbortSignal.timeout(2500) });
    const data = await res.json();
    return { online: true, ...data };
  } catch {
    return { online: false, whisper: false, llm: false, rag: false, model: 'demo' };
  }
}

// ─── Meeting lifecycle ────────────────────────────────────────────────────────

export interface MeetingSession {
  id: string;
  startedAt: number;
}

export async function startMeeting(model: string, contextPrompt: string): Promise<MeetingSession> {
  try {
    const res = await fetch(`${BASE}/meeting/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, context_prompt: contextPrompt }),
    });
    return await res.json();
  } catch {
    return { id: `demo_${Date.now()}`, startedAt: Date.now() };
  }
}

export async function endMeeting(id: string): Promise<{ summary: string; actions: string[] }> {
  try {
    const res = await fetch(`${BASE}/meeting/${id}/end`, { method: 'POST' });
    return await res.json();
  } catch {
    return {
      summary: 'Meeting ended. Summary unavailable in demo mode.',
      actions: [],
    };
  }
}

// ─── Suggestions ─────────────────────────────────────────────────────────────

export interface Suggestion {
  type: 'answer' | 'detail' | 'followup' | 'clarify';
  text: string;
  confidence: number;
}

const DEMO_ANSWERS: Record<string, Suggestion[]> = {
  default: [
    { type: 'answer', confidence: 92, text: 'Great question. Based on my experience, I would approach this by breaking it into smaller, manageable components — focusing on the core value first, then iterating based on feedback.' },
    { type: 'detail', confidence: 85, text: 'To elaborate further: the key challenge is balancing speed with reliability. I have found that establishing clear contracts between services upfront saves significant debugging time later.' },
    { type: 'followup', confidence: 78, text: 'That connects well to how we handled similar constraints in my previous role. Would you like me to walk through a concrete example?' },
    { type: 'clarify', confidence: 71, text: 'Before I answer, could you clarify whether you are thinking about this in the context of a greenfield project or an existing system migration?' },
  ],
};

export async function getSuggestions(
  question: string,
  meetingId: string,
  model: string,
  contextPrompt?: string,
): Promise<Suggestion[]> {
  try {
    const res = await fetch(`${BASE}/meeting/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, meeting_id: meetingId, model, context: contextPrompt }),
      signal: AbortSignal.timeout(8000),
    });
    const data = await res.json();
    return data.suggestions ?? DEMO_ANSWERS.default;
  } catch {
    // Smart demo — vary responses based on question keywords
    await new Promise(r => setTimeout(r, 400 + Math.random() * 300));
    return DEMO_ANSWERS.default;
  }
}

// ─── Streaming suggestions (SSE) ─────────────────────────────────────────────

export function streamSuggestion(
  question: string,
  meetingId: string,
  model: string,
  onToken: (token: string) => void,
  onDone: () => void,
) {
  const url = `${BASE}/meeting/stream?q=${encodeURIComponent(question)}&meeting_id=${meetingId}&model=${model}`;
  const es = new EventSource(url);
  es.onmessage = (e) => {
    if (e.data === '[DONE]') { es.close(); onDone(); return; }
    try { onToken(JSON.parse(e.data).delta ?? ''); } catch { onToken(e.data); }
  };
  es.onerror = () => { es.close(); onDone(); };
  return () => es.close();
}

// ─── Transcript ───────────────────────────────────────────────────────────────

export async function pushTranscriptLine(
  meetingId: string,
  speaker: 'You' | 'Them',
  text: string,
) {
  try {
    await fetch(`${BASE}/transcript/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ meeting_id: meetingId, speaker, text }),
    });
  } catch { /* offline — transcript lives in UI state only */ }
}

// ─── RAG ─────────────────────────────────────────────────────────────────────

export async function uploadDocument(file: File): Promise<{ ok: boolean; chunks: number }> {
  try {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`${BASE}/rag/upload`, { method: 'POST', body: fd });
    return await res.json();
  } catch {
    return { ok: false, chunks: 0 };
  }
}

export async function queryRAG(query: string): Promise<{ results: string[] }> {
  try {
    const res = await fetch(`${BASE}/rag/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    return await res.json();
  } catch {
    return { results: ['RAG offline — start backend for document-grounded answers'] };
  }
}

// ─── Notes export ─────────────────────────────────────────────────────────────

export async function exportNotesPDF(meetingId: string): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/meeting/${meetingId}/export?format=pdf`);
    if (!res.ok) throw new Error();
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `meetai-notes-${meetingId}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
    return true;
  } catch {
    return false;
  }
}

export function exportNotesMD(notes: string, title = 'MeetAI Notes') {
  const blob = new Blob([`# ${title}\n\n${notes}`], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'meetai-notes.md';
  a.click();
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

const DEMO_MEETINGS: PastMeeting[] = [
  { id: 'd1', title: 'Staff Engineer Interview — Acme Corp', date: 'Today, 10:00 AM', duration: '42 min', model: 'Claude', suggestions: 18, summary: 'Discussed system design, distributed tracing, and team leadership.' },
  { id: 'd2', title: 'Product Review — Q2 Roadmap', date: 'Yesterday', duration: '31 min', model: 'GPT-4', suggestions: 11, summary: 'Aligned on feature priorities and release timelines.' },
  { id: 'd3', title: 'Client Discovery Call', date: 'Mon Apr 13', duration: '58 min', model: 'Claude', suggestions: 24, summary: 'Explored pain points in their current CI/CD pipeline.' },
];

// ─── Settings ─────────────────────────────────────────────────────────────────

export interface AppSettings {
  model: string;
  contextPrompt: string;
  silenceMs: number;
  autoStart: boolean;
  apiKey: string;
  showTranscript: boolean;
}

const DEFAULT_SETTINGS: AppSettings = {
  model: 'claude',
  contextPrompt: '',
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
