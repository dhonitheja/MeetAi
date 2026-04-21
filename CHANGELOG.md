# Changelog 📜

All notable changes to the MeetAI project will be documented in this file.

---

## [v1.0.0] - "The Identity Update" - 2026-04-21

Our official production release after 7 sprints of development.

### Added
- **Final QA & Deployment (Sprint 7):**
  - Full E2E Test Suite using Playwright for Electron.
  - Performance Profiler for throughput and latency benchmarking.
  - Professional Documentation Suite (README, ARCHITECTURE, SECURITY).
  - Automated GitHub Release workflow for code-signed binaries.

- **Hardening & Billing (Sprint 6):**
  - Integrated Stripe for subscription tier management (Free, Pro, Team).
  - Implemented `slowapi` rate-limiting on all backend endpoints.
  - Structured JSON logging with `structlog`.
  - NSIS Installer bundling both Electron and Python components.

- **Unified Personas (Sprint 5):**
  - Atomic identity profiles bundling voice + face + AI behavior.
  - New Overlay UI with tabbed navigation and glassmorphic aesthetic.
  - Integrated `electron-updater` for signed background updates.

- **Intelligence & RAG (Sprint 4):**
  - Real-time RAG Co-pilot using ChromaDB and LangChain.
  - Recall.ai integration for automated meeting bot participation.
  - HMAC-based webhook validation for external services.

- **Stealth & Face Cloning (Sprint 3):**
  - Live face swapping using InsightFace (ONNX).
  - OS-level screen capture exclusion (`SetWindowDisplayAffinity`).
  - Stealth overlay window that hides from screen shares.

- **Voice Synthesis (Sprint 2):**
  - Real-time voice cloning via VoxCPM2.
  - Virtual microphone integration (VB-Audio Cable).
  - Encrypted local profile storage (Fernet + PBKDF2).

- **Core Engine (Sprint 1):**
  - Fast-API sidecar with multi-LLM support (Gemini, Claude, OpenAI).
  - Rolling transcript buffer for context management.
  - Base stealth overlay logic.

### Fixed
- Standardized API port across all components to 8765.
- Fixed `m-01` memory leak in rolling transcript buffer.
- Patched `M-new-01` regex bypass vulnerability in meeting router.
- Synchronized IPC event names between UI and Auto-updater.

### Security
- Reached a final security audit score of **9/10** (SA-06).
- All identification patterns strictly use `re.fullmatch()`.
- Zero-persistence policy enforced for biometric data.

---

## [v0.1.0-alpha] - 2026-03-20
- Initial prototype launch for the "Stealth Assistant" concept.
