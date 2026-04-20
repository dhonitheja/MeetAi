# ◈ MeetAI — Invisible AI Co-pilot for Every Call

> **Zero typing. Zero clicking. Real-time AI suggestions while you're live.**  
> Invisible to OBS, Zoom, Teams, Meet, and browser screen sharing.

---

## What it does (like Cluely / Cheating Daddy)

| Feature | Detail |
|---------|--------|
| 🛡️ **Invisible to screen share** | `WDA_EXCLUDEFROMCAPTURE` (Windows DWM level) — defeats OBS, Zoom, Teams, Chrome |
| 🎤 **Dual audio capture** | WASAPI loopback for system audio + sounddevice for mic — no virtual devices |
| 🤫 **Zero interaction** | AI suggestions trigger automatically when they stop talking |
| 📸 **Screenshot + Vision** | Press F11 → AI reads your screen (code, questions, slides) |
| 🧠 **Local-first** | Whisper (CPU int8), Silero VAD, ChromaDB — all on-device, nothing in the cloud |
| 📄 **Document RAG** | Upload your resume/CV/docs → AI answers using your actual experience |
| 📝 **Rolling summary** | Auto-generates meeting notes, action items, and decisions |
| 🔑 **Global hotkeys** | F9 hide/show, F10 copy answer, F11 screenshot, Ctrl+Shift+M click-through |
| 🖥️ **Process disguise** | Shows as "Windows Audio Device Graph" in Task Manager |

---

## Quick Start (5 minutes)

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Copy and configure `.env`

```bash
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY or OPENAI_API_KEY
```

### 3. Launch everything

```bash
python start.py
```

This starts:
- **FastAPI backend** at `http://127.0.0.1:8765`
- **PyQt6 stealth overlay** (invisible to screen capture)
- **Audio engine** (mic + system audio capture)

### 4. Open the web dashboard (optional)

```bash
npm install
npm run dev
# → http://localhost:5174
```

---

## Hotkeys (global — work even when overlay is hidden)

| Key | Action |
|-----|--------|
| `F9` | Toggle overlay visibility |
| `F10` | Copy top AI suggestion to clipboard |
| `F11` | Screenshot + Vision AI analysis |
| `Ctrl+Shift+M` | Toggle click-through mode |

---

## How it works in a real call

1. **Open your meeting** in Zoom/Teams/Meet (any tab or app)
2. **Launch MeetAI**: `python start.py`
3. The overlay appears — **drag it to a corner** of your screen
4. Start your call — MeetAI listens to **both sides** automatically:
   - Your mic → transcribed as **You**
   - Meeting audio → transcribed as **Them** via WASAPI loopback
5. When **they stop talking**, MeetAI auto-generates suggestions
6. Press **F10 to copy** the best answer to clipboard

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 STEALTH OVERLAY                  │
│   PyQt6  •  WDA_EXCLUDEFROMCAPTURE  •  Hotkeys  │
│   Tabs: Suggestions / Transcript / Notes / Settings │
└───────────────┬─────────────────────────────────┘
                │ REST + SSE
┌───────────────▼─────────────────────────────────┐
│              FASTAPI BACKEND  :8765              │
│  /meeting/ask   → LiteLLM (Claude/GPT/Ollama)   │
│  /rag/upload    → ChromaDB + sentence-transformers│
│  /screenshot/analyze → Vision AI (GPT-4V/Claude)│
│  /meeting/export → MD / PDF / DOCX              │
└───────────────┬─────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────┐
│            AUDIO ENGINE                         │
│  Mic: sounddevice → Silero VAD → faster-whisper │
│  Sys: WASAPI loopback → Silero VAD → whisper    │
└─────────────────────────────────────────────────┘
```

---

## Stealth: Why it works

On Windows 10/11 (build 19041+):
- `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` runs at the **DWM compositor level**
- The window literally doesn't exist in the captured framebuffer
- OBS, Zoom, Teams, Chrome screen share — **all defeated** without any workaround

On macOS ≤ 14:
- `NSWindow.sharingType = NSWindowSharingNone` blocks legacy CoreGraphics capture
- Chrome/browser sharing, Teams, older Zoom: ✅ invisible
- macOS 15 Sequoia broke this with ScreenCaptureKit — use browser-based meetings

---

## Document RAG (upload your CV/notes)

```bash
# Via web dashboard → Documents tab
# Or via API:
curl -X POST http://127.0.0.1:8765/rag/upload \
  -F "file=@/path/to/your-cv.pdf"
```

The AI will now answer questions using your actual experience, projects, and background.

---

## Build standalone binary

```bash
pip install pyinstaller
pyinstaller packaging/meetai.spec
# Output: dist/MeetAI/MeetAI.exe
```

---

## Requirements

- **Python 3.11+**
- **Windows 10 build 19041+** (for bulletproof stealth)
- **Chrome/Edge** (for browser dashboard)
- **API key**: Anthropic, OpenAI, or local Ollama

---

## License

MIT — Fork freely. Star if it helps. 🌟
