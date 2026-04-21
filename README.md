# MeetAI: The Stealth AI Meeting Assistant 🎭🤖

**Unseen. Untraceable. Unstoppable.**
MeetAI is a production-grade, zero-interaction SaaS meeting assistant that integrates real-time voice cloning, face swapping, and RAG-driven co-pilot suggestions into one stealthy, screen-exclusion overlay.

---

## 🚀 Key Features

- **🎭 Real-Time Voice Cloning:** Powered by VoxCPM2, switch your identity instantly with 48kHz high-fidelity output via a virtual microphone.
- **👤 Live Face Swapping:** Leverage InsightFace for seamless, low-latency face cloning on any video stream using OBS Virtual Camera.
- **🤖 RAG Co-Pilot:** Real-time Whisper transcription feeding into LangChain and ChromaDB to surface document-grounded suggestions and action items.
- **📞 Recall.ai Meeting Bot:** An automated bot that joins Zoom, Teams, or Google Meet to provide real-time diarized transcripts directly to your dashboard.
- **👻 Stealth Overlay:** A specialized Electron shell using `SetWindowDisplayAffinity` to remain completely invisible to screen-sharing and recording software.

---

## 💻 Hardware Requirements

To ensure smooth 24+ FPS face swapping and <200ms voice synthesis latency, the following is required:

| Component | Minimum | Recommended |
| :--- | :--- | :--- |
| **GPU** | NVIDIA RTX 2060 (6GB VRAM) | NVIDIA RTX 3070 (8GB VRAM) |
| **OS** | Windows 10 v2004+ / macOS 12+ | Windows 11 / macOS 14+ |
| **RAM** | 16GB | 32GB+ |
| **Driver** | CUDA 11.8+ (for Windows) | Latest Apple Silicon (M2+) |

---

## 🛠️ Setup & Installation

### 1. External Dependencies
- **Virtual Audio:** Install [VB-Audio Cable](https://vb-audio.com/Cable/) (Windows) or [BlackHole](https://existential.audio/blackhole/) (macOS).
- **Virtual Camera:** Install [OBS Studio](https://obsproject.com/) and enable the **Virtual Camera** feature.

### 2. Model Downloads
You must manually place the following model weights in `./models/`:
- **VoxCPM2:** Download from [HuggingFace (openbmb/VoxCPM2)](https://huggingface.co/openbmb/VoxCPM2).
- **InsightFace:** Download `inswapper_128.onnx` from [HuggingFace (deepinsight/inswapper)](https://huggingface.co/deepinsight/inswapper).

### 3. Quick Start
```bash
# 1. Clone the repository
git clone https://github.com/dhonitheja/MeetAi.git
cd MeetAi

# 2. Configure Environment
cp .env.example .env
# Edit .env with your Stripe, Recall, and LLM API keys

# 3. Install Python Sidecar
pip install -r requirements.txt

# 4. Install Frontend & Build
npm install
npm run build

# 5. Launch (Multi-process)
# Tab 1: ML Backend
python start.py
# Tab 2: Electron Desktop App
npm start
```

---

## 📚 Documentation
- [Architecture & Data Flow](ARCHITECTURE.md)
- [API Reference](API.md)
- [Security & Privacy Standards](SECURITY.md)
- [Release Changelog](CHANGELOG.md)

---

## ⚖️ License
Proprietary. All rights reserved. For commercial licensing, contact [dhonitheja@example.com].
