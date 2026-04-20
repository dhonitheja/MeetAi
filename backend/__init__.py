"""
MeetAI Python Backend
=====================
FastAPI server powering audio capture, real-time transcription, LLM suggestions,
RAG pipeline, stealth overlay control, and meeting notes export.

Architecture:
  src/
    audio/
      capture.py        — WASAPI loopback (Windows) + mic dual-channel capture
      vad.py            — Silero VAD pre-filter
    transcription/
      engine.py         — faster-whisper real-time transcription
    llm/
      provider.py       — LiteLLM switchable backend (Claude / GPT-4 / Ollama)
      prompts.py        — Structured prompt templates
    rag/
      pipeline.py       — ChromaDB + MiniLM-L6-v2 document indexing & retrieval
      loader.py         — PDF / DOCX / TXT document loaders
    ui/
      stealth.py        — SetWindowDisplayAffinity / NSWindow stealth wrappers
      overlay.py        — PyQt6 frameless overlay window
    summarizer/
      rolling.py        — Sliding-window live summarization
      action_items.py   — JSON action-item extraction
      exporter.py       — Markdown / PDF (fpdf2) / DOCX export
    server.py           — FastAPI main entry point
    config.py           — Settings and API key management
"""

# ─── requirements.txt reference (install with: pip install -r requirements.txt) ───
REQUIREMENTS = """
# UI overlay
PyQt6>=6.6.0
pyobjc-framework-Cocoa>=10.0; sys_platform == "darwin"

# Audio
PyAudioWPatch>=0.2.12; sys_platform == "win32"
sounddevice>=0.4.6

# Transcription
faster-whisper>=1.0.0
silero-vad>=6.0.0

# LLM
litellm>=1.50.0
anthropic>=0.90.0
openai>=1.50.0

# RAG
chromadb>=0.5.0
sentence-transformers>=3.0.0
langchain>=0.5.0
langchain-chroma>=0.2.0

# Document loaders + export
pypdf>=4.0.0
python-docx>=1.0.0
fpdf2>=2.8.0
docx2txt>=0.8

# API server
fastapi>=0.115.0
uvicorn[standard]>=0.30.0

# Utilities
numpy>=1.24.0
pynput>=1.7.6
keyring>=25.0.0
"""
