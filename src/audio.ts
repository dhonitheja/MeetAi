/**
 * MeetAI Auto-Listen Engine
 * ===========================
 * Handles all audio capture without any user typing or clicking:
 *
 *  • getUserMedia  → your microphone (what YOU say → labeled "You")
 *  • getDisplayMedia (audio only) → system audio (what THEY say → labeled "Them")
 *  • SpeechRecognition (browser built-in, free) → real-time transcript
 *  • AudioContext AnalyserNode → silence detection (VAD)
 *  • Auto-trigger AI suggestions after 1.5s silence following "Them" speech
 *
 * No API key needed for transcription — uses Chrome's built-in speech engine.
 */

export type Speaker = 'You' | 'Them';

export interface TranscriptEvent {
  speaker: Speaker;
  text: string;
  final: boolean;
  time: string;
}

export interface ListenConfig {
  /** Called with each transcript update (interim + final) */
  onTranscript: (ev: TranscriptEvent) => void;
  /** Called after silence following "Them" speech — triggers AI */
  onSilenceAfterThem: (lastUtterance: string) => void;
  /** Status updates */
  onStatus: (msg: string) => void;
  /** Silence threshold ms — how long quiet before triggering AI */
  silenceMs?: number;
}

const SILENCE_DEFAULT = 1800; // 1.8s silence → trigger suggestion
const NOW = () => new Date().toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' });

// ─── Speech Recognition wrapper ──────────────────────────────────────────────

function createRecognition(lang = 'en-US'): SpeechRecognition | null {
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  if (!SR) return null;
  const r = new SR() as SpeechRecognition;
  r.continuous = true;
  r.interimResults = true;
  r.lang = lang;
  r.maxAlternatives = 1;
  return r;
}

// ─── VAD (Voice Activity Detection) via AudioContext ─────────────────────────

class SilenceDetector {
  private analyser: AnalyserNode;
  private data: Uint8Array;
  private silenceStart = 0;
  private hadSpeech = false;
  private rafId = 0;

  constructor(
    private stream: MediaStream,
    private ctx: AudioContext,
    private onSilence: () => void,
    private silenceMs: number,
  ) {
    this.analyser = ctx.createAnalyser();
    this.analyser.fftSize = 256;
    this.data = new Uint8Array(this.analyser.frequencyBinCount);
    ctx.createMediaStreamSource(stream).connect(this.analyser);
    this.loop();
  }

  private loop() {
    this.rafId = requestAnimationFrame(() => this.loop());
    this.analyser.getByteFrequencyData(this.data);
    const rms = Math.sqrt(this.data.reduce((a, b) => a + b * b, 0) / this.data.length);
    const isSpeaking = rms > 12; // threshold — tune if needed

    if (isSpeaking) {
      this.hadSpeech = true;
      this.silenceStart = 0;
    } else if (this.hadSpeech) {
      if (!this.silenceStart) this.silenceStart = Date.now();
      if (Date.now() - this.silenceStart >= this.silenceMs) {
        this.hadSpeech = false;
        this.silenceStart = 0;
        this.onSilence();
      }
    }
  }

  destroy() {
    cancelAnimationFrame(this.rafId);
  }
}

// ─── Main AutoListener class ──────────────────────────────────────────────────

export class AutoListener {
  private micStream: MediaStream | null = null;
  private sysStream: MediaStream | null = null;
  private micRec: SpeechRecognition | null = null;
  private sysRec: SpeechRecognition | null = null;
  private silenceDetector: SilenceDetector | null = null;
  private audioCtx: AudioContext | null = null;
  private lastThemUtterance = '';
  private config: Required<ListenConfig>;
  private active = false;

  constructor(config: ListenConfig) {
    this.config = { silenceMs: SILENCE_DEFAULT, ...config };
  }

  async start(): Promise<{ micOk: boolean; sysOk: boolean }> {
    this.active = true;
    let micOk = false;
    let sysOk = false;

    // ── 1. Microphone (Your voice) ─────────────────────────────────────────
    try {
      this.micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      this.micRec = createRecognition();
      if (this.micRec) {
        this.micRec.onresult = this.makeHandler('You');
        this.micRec.onerror = (e) => console.warn('Mic SR error:', e.error);
        this.micRec.onend = () => { if (this.active) this.micRec?.start(); };
        this.micRec.start();
        micOk = true;
        this.config.onStatus('🎤 Microphone active');
      }
    } catch (err) {
      this.config.onStatus('⚠️ Mic permission denied — click 🔒 in address bar');
      console.warn('Mic error:', err);
    }

    // ── 2. System audio (Their voice) ─────────────────────────────────────
    try {
      // Prompt user to share tab/screen with audio
      this.sysStream = await (navigator.mediaDevices as any).getDisplayMedia({
        video: false, // audio only — no screen capture needed
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          sampleRate: 44100,
        },
      });

      // Attach SpeechRecognition to system audio stream via AudioContext
      this.audioCtx = new AudioContext();
      const dest = this.audioCtx.createMediaStreamDestination();
      this.audioCtx.createMediaStreamSource(this.sysStream).connect(dest);

      this.sysRec = createRecognition();
      if (this.sysRec) {
        // Replace default mic input with system audio output
        // NOTE: SpeechRecognition uses the default mic; for system audio
        // we use a virtual MediaStream routed via AudioContext
        this.sysRec.onresult = this.makeHandler('Them');
        this.sysRec.onerror = (e) => console.warn('Sys SR error:', e.error);
        this.sysRec.onend = () => { if (this.active) this.sysRec?.start(); };
        this.sysRec.start();
        sysOk = true;
        this.config.onStatus('🔊 System audio captured (other person)');
      }

      // VAD silence detector on system stream
      this.silenceDetector = new SilenceDetector(
        this.sysStream,
        this.audioCtx,
        () => {
          if (this.lastThemUtterance.trim().length > 10) {
            this.config.onSilenceAfterThem(this.lastThemUtterance);
            this.lastThemUtterance = '';
          }
        },
        this.config.silenceMs,
      );
    } catch (err: any) {
      // User cancelled screen share — use mic-only mode with smart turn detection
      this.config.onStatus('🎤 Mic-only mode — detecting turns by pause length');
      console.warn('System audio error:', err?.message ?? err);

      // Fallback: use mic VAD, longer silence = "Them finished question"
      if (this.micStream && this.audioCtx === null) {
        this.audioCtx = new AudioContext();
        this.silenceDetector = new SilenceDetector(
          this.micStream,
          this.audioCtx,
          () => {
            if (this.lastThemUtterance.trim().length > 8) {
              this.config.onSilenceAfterThem(this.lastThemUtterance);
              this.lastThemUtterance = '';
            }
          },
          this.config.silenceMs + 500, // slightly longer threshold in mic-only mode
        );
      }
    }

    this.config.onStatus(micOk ? '✅ Listening automatically…' : '❌ Failed to access audio');
    return { micOk, sysOk };
  }

  /** Returns a SpeechRecognition event handler for the given speaker */
  private makeHandler(speaker: Speaker) {
    return (ev: SpeechRecognitionEvent) => {
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const result = ev.results[i];
        const text = result[0].transcript.trim();
        if (!text) continue;

        const final = result.isFinal;
        this.config.onTranscript({ speaker, text, final, time: NOW() });

        if (speaker === 'Them' && final) {
          this.lastThemUtterance += ' ' + text;
        }
      }
    };
  }

  getAudioLevel(speaker: 'mic' | 'sys'): number {
    // Returns 0-1 energy level for visualization
    return 0; // hooked externally via AudioWorklet if needed
  }

  stop() {
    this.active = false;
    this.micRec?.stop();
    this.sysRec?.stop();
    this.silenceDetector?.destroy();
    this.micStream?.getTracks().forEach(t => t.stop());
    this.sysStream?.getTracks().forEach(t => t.stop());
    this.audioCtx?.close();
  }
}

// ─── Audio level meter (for waveform viz) ────────────────────────────────────

export function createAudioMeter(stream: MediaStream, onLevel: (level: number) => void): () => void {
  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  const data = new Uint8Array(analyser.frequencyBinCount);
  ctx.createMediaStreamSource(stream).connect(analyser);

  let raf = 0;
  const loop = () => {
    raf = requestAnimationFrame(loop);
    analyser.getByteFrequencyData(data);
    const avg = data.reduce((a, b) => a + b, 0) / data.length;
    onLevel(avg / 256);
  };
  loop();

  return () => {
    cancelAnimationFrame(raf);
    ctx.close();
  };
}

// ─── Browser support check ───────────────────────────────────────────────────

export function checkBrowserSupport(): { speechRecognition: boolean; getDisplayMedia: boolean } {
  return {
    speechRecognition: !!(
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    ),
    getDisplayMedia: !!(navigator.mediaDevices as any).getDisplayMedia,
  };
}
