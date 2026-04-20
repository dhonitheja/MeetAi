// ─── Types ─────────────────────────────────────────────────────────────────

export type Screen = 'home' | 'setup' | 'meeting' | 'notes' | 'docs';
export type AIModel = 'claude' | 'gpt4' | 'gemini' | 'ollama';

export interface TranscriptLine {
  id: number;
  speaker: 'You' | 'Them';
  text: string;
  time: string;
}

export interface Suggestion {
  id: number;
  type: 'answer' | 'detail' | 'followup' | 'clarify';
  label: string;
  icon: string;
  text: string;
  confidence: number;
}

export interface Document {
  id: string;
  name: string;
  size: string;
  status: 'indexed' | 'processing' | 'error';
  chunks?: number;
}

export interface Meeting {
  id: string;
  title: string;
  date: string;
  duration: string;
  model: AIModel;
  notes: string;
}

// ─── Mock Data ──────────────────────────────────────────────────────────────

export const MOCK_TRANSCRIPT: TranscriptLine[] = [
  { id: 1, speaker: 'Them', text: 'Can you walk us through your approach to microservices architecture?', time: '10:02' },
  { id: 2, speaker: 'You', text: 'Sure! We use Spring Boot with an API gateway pattern backed by Netflix Eureka for service discovery.', time: '10:03' },
  { id: 3, speaker: 'Them', text: 'How do you handle service-to-service authentication in that setup?', time: '10:04' },
  { id: 4, speaker: 'Them', text: "And what's your experience with distributed tracing?", time: '10:05' },
];

export const MOCK_SUGGESTIONS: Suggestion[] = [
  {
    id: 1, type: 'answer', label: 'Answer', icon: '💬', confidence: 94,
    text: 'We use JWT tokens with a shared secret rotated via Vault, combined with mTLS for internal service calls. Each service validates tokens against an Auth service with a 5-minute TTL cache to reduce latency.',
  },
  {
    id: 2, type: 'detail', label: 'More Detail', icon: '📚', confidence: 88,
    text: 'For distributed tracing, we implemented OpenTelemetry with Jaeger as the backend. Each request gets a trace ID propagated through HTTP headers. We correlate logs in ELK stack using this trace ID for end-to-end visibility.',
  },
  {
    id: 3, type: 'followup', label: 'Follow-up Q', icon: '🔄', confidence: 81,
    text: 'Great question — we also implemented circuit breakers using Resilience4j. Would you like me to walk through a specific failure scenario we handled in production?',
  },
  {
    id: 4, type: 'clarify', label: 'Clarify', icon: '🎯', confidence: 76,
    text: "When you mention distributed tracing — are you asking about inter-service tracing specifically, or also client-side performance monitoring? Our approach differs slightly for each.",
  },
];

export const MOCK_NOTES = `## Meeting Notes — April 15, 2026

### Key Points
- Discussed microservices architecture with Spring Boot and Netflix Eureka
- Service auth: JWT + mTLS pattern with Vault secret rotation
- Distributed tracing: OpenTelemetry + Jaeger for end-to-end visibility
- Circuit breakers via Resilience4j for fault tolerance

### Action Items
- [ ] Share architecture diagram by Friday
- [ ] Send link to OpenTelemetry setup guide
- [ ] Follow up on team size and on-call rotation question
- [ ] Schedule technical deep-dive for next week

### Decisions
- Will proceed with API Gateway pattern over BFF
- Jaeger preferred over Zipkin for new microservices setup
- mTLS required for all internal service calls going forward`;

export const MOCK_MEETINGS: Meeting[] = [
  { id: '1', title: 'Engineering Standup', date: 'Today, 9:00 AM', duration: '22 min', model: 'claude', notes: MOCK_NOTES },
  { id: '2', title: 'Product Design Review', date: 'Yesterday', duration: '47 min', model: 'gpt4', notes: MOCK_NOTES },
  { id: '3', title: 'Staff Engineer Interview', date: 'Mon Apr 13', duration: '58 min', model: 'claude', notes: MOCK_NOTES },
];

export const MOCK_DOCUMENTS: Document[] = [
  { id: '1', name: 'Resume_2026.pdf', size: '142 KB', status: 'indexed', chunks: 48 },
  { id: '2', name: 'System_Design_Notes.docx', size: '88 KB', status: 'indexed', chunks: 87 },
  { id: '3', name: 'Company_Overview.pdf', size: '1.2 MB', status: 'processing' },
];

export const MODEL_LABELS: Record<AIModel, string> = {
  claude: 'Claude',
  gpt4: 'GPT-4',
  gemini: 'Gemini',
  ollama: 'Ollama',
};
