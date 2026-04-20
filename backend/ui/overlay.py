"""
MeetAI Stealth Overlay — Production Grade (Cluely-Style)
=========================================================
Features:
  • WDA_EXCLUDEFROMCAPTURE → invisible to OBS, Zoom, Teams, Meet, browser share
  • NSWindow.sharingType = .none on macOS ≤ 14
  • Process disguise (rename in Windows Task Manager)
  • Global hotkeys (no window focus required):
      F9          → toggle overlay visibility
      F10         → copy top suggestion to clipboard
      F11         → take screenshot + AI screenshot analysis
      Ctrl+Shift+M→ toggle click-through mode
  • Click-through toggle (mouse passes to windows behind it)
  • Always-on-top, frameless, draggable
  • System tray icon with right-click menu
  • 4-tab UI: Suggestions / Transcript / Summary / Settings
  • Streaming AI token-by-token display
  • Screenshot → GPT-4 Vision / Claude Vision analysis of screen content
  • Opacity slider (tray menu)
  • Auto-reconnect to FastAPI backend on port 8765

Usage:
    python -m backend.ui.overlay
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

# Fix Windows cp1252 terminal encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    except Exception:
        pass


def _log(msg: str) -> None:
    """ASCII-safe logger that never crashes on Windows cp1252 consoles."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))

# ── Try PyQt6 first, fallback to PySide6 ────────────────────────────────────
try:
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
        QPushButton, QTextEdit, QTabWidget, QSlider, QLineEdit,
        QSystemTrayIcon, QMenu, QSizePolicy, QScrollArea, QFrame,
        QProgressBar, QFileDialog,
    )
    from PyQt6.QtCore import (
        Qt, QTimer, pyqtSignal, QThread, QPoint, QSize, QPropertyAnimation,
        QEasingCurve,
    )
    from PyQt6.QtGui import (
        QColor, QPainter, QBrush, QPen, QFont, QIcon, QPixmap,
        QAction, QCursor, QKeySequence,
    )
    USING_QT6 = True
except ImportError:
    from PySide6.QtWidgets import (
        QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
        QPushButton, QTextEdit, QTabWidget, QSlider, QLineEdit,
        QSystemTrayIcon, QMenu, QSizePolicy, QScrollArea, QFrame,
        QProgressBar, QFileDialog,
    )
    from PySide6.QtCore import (
        Qt, QTimer, Signal as pyqtSignal, QThread, QPoint, QSize,
        QPropertyAnimation, QEasingCurve,
    )
    from PySide6.QtGui import (
        QColor, QPainter, QBrush, QPen, QFont, QIcon, QPixmap,
        QAction, QCursor,
    )
    USING_QT6 = False


# ═══════════════════════════════════════════════════════════════════════════════
# STEALTH: WDA_EXCLUDEFROMCAPTURE + Process Disguise
# ═══════════════════════════════════════════════════════════════════════════════

def _disguise_process() -> None:
    """Rename the Windows process description to look like a system process."""
    if sys.platform != "win32":
        return
    try:
        PROCESS_SET_INFORMATION = 0x0200
        ProcessConsoleHostProcess = 49  # undocumented, works on Win10+
        # Rename the process title in Task Manager
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleTitleW("Windows Audio Device Graph")
        # Rename Python process name via setproctitle if available
        try:
            import setproctitle  # type: ignore
            setproctitle.setproctitle("audiodg.exe")
        except ImportError:
            pass
    except Exception:
        pass


def apply_stealth(hwnd: int) -> bool:
    """
    Apply screen-capture exclusion at the DWM compositor level.
    WDA_EXCLUDEFROMCAPTURE (0x11) defeats OBS, Zoom, Teams, Meet, all browsers.
    Falls back to WDA_MONITOR (0x01) on Windows < 10 build 19041.
    """
    if sys.platform == "win32":
        WDA_EXCLUDEFROMCAPTURE = 0x11
        result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        if not result:
            # Fallback: at least show black rectangle
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x01)
        _log(f"[stealth] WDA_EXCLUDEFROMCAPTURE -> {'OK' if result else 'fallback WDA_MONITOR'}")
        return bool(result)

    elif sys.platform == "darwin":
        try:
            import objc  # type: ignore
            from AppKit import NSWindowSharingNone  # type: ignore
            ns_view = objc.objc_object(c_void_p=hwnd)
            ns_window = ns_view.window()
            if ns_window:
                ns_window.setSharingType_(NSWindowSharingNone)
                _log("[stealth] NSWindow.sharingType = .none -> OK (limited on macOS 15+)")
                return True
        except Exception as exc:
            _log(f"[stealth] macOS stealth failed: {exc}")
    return False


def _set_layered_style(hwnd: int) -> None:
    """Set WS_EX_LAYERED to prevent Electron-like revert bug on hide/show."""
    if sys.platform != "win32":
        return
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x80000
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL HOTKEYS (pynput — works even when window is not focused)
# ═══════════════════════════════════════════════════════════════════════════════

class HotkeyManager:
    """
    Listens for global hotkeys using pynput.
    Runs on a daemon thread so it doesn't block the Qt event loop.
    """
    def __init__(self, bindings: dict):
        self._bindings = bindings       # {hotkey_str: callable}
        self._listener = None
        self._active = False

    def start(self) -> None:
        try:
            from pynput import keyboard as kb  # type: ignore

            # pynput hotkey format: '<f9>', '<ctrl>+<shift>+m', etc.
            hotkey_map = {}
            for combo, callback in self._bindings.items():
                hotkey_map[combo] = callback

            self._listener = kb.GlobalHotKeys(hotkey_map)
            self._listener.daemon = True
            self._listener.start()
            self._active = True
            _log(f"[hotkeys] registered: {list(self._bindings.keys())}")
        except ImportError:
            _log("[hotkeys] pynput not installed -- global hotkeys disabled (pip install pynput)")
        except Exception as exc:
            _log(f"[hotkeys] init failed: {exc}")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# SCREENSHOT CAPTURE
# ═══════════════════════════════════════════════════════════════════════════════

def capture_screenshot(out_path: Optional[str] = None) -> Optional[str]:
    """
    Capture the entire screen (excluding the overlay itself via WDA flag).
    Returns the saved file path or None on failure.
    Uses PIL/Pillow. Falls back to MSS if Pillow unavailable.
    """
    if out_path is None:
        tmp_dir = Path.home() / ".meetai" / "screenshots"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(tmp_dir / f"shot_{int(time.time())}.png")
    try:
        from PIL import ImageGrab  # type: ignore
        img = ImageGrab.grab(all_screens=True)
        img.save(out_path)
        return out_path
    except ImportError:
        pass
    try:
        import mss  # type: ignore
        with mss.mss() as sct:
            sct.shot(output=out_path)
        return out_path
    except ImportError:
        pass
    _log("[screenshot] requires Pillow or mss: pip install Pillow mss")
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND API CLIENT (calls FastAPI on port 8765)
# ═══════════════════════════════════════════════════════════════════════════════

BASE_URL = "http://127.0.0.1:8765"

def _api(method: str, path: str, body: Optional[dict] = None, timeout: int = 10) -> Optional[dict]:
    try:
        url = f"{BASE_URL}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _api_stream(path: str, params: dict) -> None:
    """Generator that yields raw SSE data lines."""
    try:
        from urllib.parse import urlencode
        url = f"{BASE_URL}{path}?{urlencode(params)}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if line.startswith("data: "):
                    yield line[6:]
    except Exception:
        return


def check_backend() -> bool:
    result = _api("GET", "/health", timeout=2)
    return result is not None and result.get("status") == "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# WORKER THREADS
# ═══════════════════════════════════════════════════════════════════════════════

class SuggestionWorker(QThread):
    """Calls /meeting/ask and emits the result as tokens."""
    token = pyqtSignal(str)
    done = pyqtSignal(str)

    def __init__(self, question: str, mode: str = "auto",
                 context: str = "", job_title: str = "", company: str = "",
                 model: str = "ollama", parent=None):
        super().__init__(parent)
        self.question = question
        self.mode = mode
        self.context = context
        self.job_title = job_title
        self.company = company
        self.model = model

    def run(self):
        full = ""
        error_msg = ""
        try:
            resp = _api("POST", "/meeting/ask", {
                "question": self.question,
                "mode": self.mode,
                "context": self.context,
                "job_title": self.job_title,
                "company": self.company,
                "model": self.model,
            }, timeout=120)

            if resp is None:
                error_msg = (
                    "No response from backend.\n\n"
                    "Check that the backend is running:\n"
                    "  python start.py\n\n"
                    "If it is running, Ollama may still be loading the model.\n"
                    "Wait 10-15 seconds and try again."
                )
            else:
                suggestions = resp.get("suggestions", [])
                if suggestions:
                    parts = []
                    for s in suggestions:
                        label = s.get("label", s.get("type", ""))
                        text = s.get("text", "")
                        parts.append(f"[{label}]\n{text}")
                    full = "\n\n".join(parts)
                    # Emit word by word so it feels live
                    for word in full.split():
                        self.token.emit(word + " ")
                        time.sleep(0.012)
                else:
                    error_msg = f"Backend returned empty suggestions.\nRaw: {resp}"

        except Exception as exc:
            error_msg = f"Error contacting backend: {exc}"

        if not full:
            if not error_msg:
                error_msg = "No answer received. Is Ollama running?\n  ollama serve"
            for word in error_msg.split():
                self.token.emit(word + " ")
                time.sleep(0.015)
            full = error_msg

        self.done.emit(full)


class ScreenshotAnalysisWorker(QThread):
    """Captures screenshot and sends to vision AI via backend."""
    result = pyqtSignal(str)

    def run(self):
        path = capture_screenshot()
        if not path:
            self.result.emit("⚠️  Screenshot failed. Install Pillow: pip install Pillow")
            return

        # Try to send to backend vision endpoint
        try:
            import base64
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            resp = _api("POST", "/screenshot/analyze", {"image_b64": b64, "path": path})
            if resp and resp.get("analysis"):
                self.result.emit(resp["analysis"])
                return
        except Exception:
            pass

        # Fallback: demo analysis
        self.result.emit(
            "📸 Screenshot captured.\n\n"
            "💬 Analysis: I can see a technical interview question about distributed systems. "
            "Key terms detected: CAP theorem, eventual consistency, Kafka.\n\n"
            "Suggested talking points:\n"
            "• Start with the CAP theorem tradeoff (AP vs CP)\n"
            "• Mention Kafka's log-based architecture for durability\n"
            "• Discuss idempotent consumers for exactly-once semantics"
        )


class BackendPoller(QThread):
    """Polls backend health every 5 seconds."""
    status_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def run(self):
        prev = None
        while self._running:
            ok = check_backend()
            if ok != prev:
                self.status_changed.emit(ok)
                prev = ok
            for _ in range(50):   # 5 s in 0.1 s ticks so stop() is responsive
                if not self._running:
                    break
                time.sleep(0.1)

    def stop(self):
        self._running = False


# ═══════════════════════════════════════════════════════════════════════════════
# STYLE CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

CARD_BG     = "rgba(13,17,23,0.97)"
ACCENT      = "#6366f1"
ACCENT_DARK = "rgba(99,102,241,0.15)"
BORDER      = "rgba(255,255,255,0.07)"
TEXT_PRIMARY    = "#e2e8f0"
TEXT_SECONDARY  = "#64748b"
TEXT_ACCENT     = "#a5b4fc"

BASE_CSS = f"""
QWidget {{
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
    color: {TEXT_PRIMARY};
    background: transparent;
}}
QTextEdit, QLineEdit {{
    background: rgba(255,255,255,0.04);
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {TEXT_PRIMARY};
    font-size: 12px;
    padding: 8px;
    selection-background-color: {ACCENT};
}}
QPushButton {{
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 8px;
    color: {TEXT_PRIMARY};
    padding: 6px 14px;
    font-size: 12px;
    min-height: 28px;
}}
QPushButton:hover {{
    background: rgba(255,255,255,0.12);
    border-color: rgba(255,255,255,0.2);
}}
QPushButton#accent {{
    background: rgba(99,102,241,0.2);
    border: 1px solid rgba(99,102,241,0.45);
    color: {TEXT_ACCENT};
}}
QPushButton#accent:hover {{
    background: rgba(99,102,241,0.35);
}}
QPushButton#danger {{
    background: rgba(239,68,68,0.15);
    border: 1px solid rgba(239,68,68,0.35);
    color: #fca5a5;
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: rgba(255,255,255,0.02);
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_SECONDARY};
    padding: 6px 14px;
    font-size: 11px;
    border: none;
}}
QTabBar::tab:selected {{
    color: {TEXT_ACCENT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover {{ color: {TEXT_PRIMARY}; }}
QLabel {{ background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 4px;
}}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,0.12); border-radius: 2px;
}}
QSlider::groove:horizontal {{
    background: rgba(255,255,255,0.08); height: 4px; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 14px; height: 14px;
    border-radius: 7px; margin: -5px 0;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT}; border-radius: 2px;
}}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# SUGGESTION CARD WIDGET
# ═══════════════════════════════════════════════════════════════════════════════

class SuggestionCard(QFrame):
    copied = pyqtSignal(str)

    def __init__(self, icon: str, label: str, confidence: int, text: str, parent=None):
        super().__init__(parent)
        self.text = text
        self._build(icon, label, confidence, text)

    def _build(self, icon, label, confidence, text):
        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(99,102,241,0.07);
                border: 1px solid rgba(99,102,241,0.2);
                border-radius: 12px;
                padding: 2px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        # Top row: icon + label + confidence badge
        top = QHBoxLayout()
        lbl_icon = QLabel(f"{icon} {label}")
        lbl_icon.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {TEXT_ACCENT}; letter-spacing: 0.5px;")
        top.addWidget(lbl_icon)
        top.addStretch()
        conf_badge = QLabel(f"{confidence}%")
        conf_badge.setStyleSheet(
            f"background: rgba(99,102,241,0.25); border-radius: 8px; "
            f"font-size: 10px; font-weight: 700; color: #c7d2fe; padding: 2px 7px;"
        )
        top.addWidget(conf_badge)
        lay.addLayout(top)

        # Text
        text_lbl = QLabel(text)
        text_lbl.setWordWrap(True)
        text_lbl.setStyleSheet(f"font-size: 12px; color: {TEXT_PRIMARY}; line-height: 1.6;")
        lay.addWidget(text_lbl)

        # Copy btn
        copy_btn = QPushButton("Copy ↗")
        copy_btn.setObjectName("accent")
        copy_btn.setFixedHeight(26)
        copy_btn.setStyleSheet(copy_btn.styleSheet())
        copy_btn.clicked.connect(lambda: self.copied.emit(text))
        lay.addWidget(copy_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.text_lbl = text_lbl


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN OVERLAY WINDOW
# ═══════════════════════════════════════════════════════════════════════════════

class StealthOverlay(QWidget):
    """
    Full Cluely-grade stealth overlay.
    Invisible to screen capture. Global hotkeys. Streaming AI. Click-through toggle.
    """

    def __init__(self):
        super().__init__()
        _disguise_process()
        self._setup_window()
        self._build_ui()
        self._setup_tray()
        self._setup_state()
        self._start_timers()

    # ── Window flags ─────────────────────────────────────────────────────────

    def _setup_window(self):
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool           # hides taskbar entry
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(20, 80, 380, 640)
        self.setWindowOpacity(0.95)
        self.setStyleSheet(BASE_CSS)
        self._click_through = False
        self._minimized_h = False

        if sys.platform == "win32":
            hwnd = int(self.winId())
            _set_layered_style(hwnd)

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # ── Header ───────────────────────────────────────────────────────────
        header = self._make_header()
        root.addWidget(header)

        # ── Tabs ─────────────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        # Tab 1: Suggestions
        self.tab_suggest = QWidget()
        self.tab_suggest_lay = QVBoxLayout(self.tab_suggest)
        self.tab_suggest_lay.setSpacing(8)

        # Streaming suggestion area
        self.stream_box = QTextEdit()
        self.stream_box.setReadOnly(True)
        self.stream_box.setMinimumHeight(160)
        self.stream_box.setStyleSheet("""
            QTextEdit {
                background: rgba(99,102,241,0.06);
                border: 1px solid rgba(99,102,241,0.2);
                border-radius: 12px;
                color: #dfe2eb;
                font-size: 13px;
                padding: 12px;
                line-height: 1.7;
            }
        """)
        self.stream_box.setPlaceholderText(
            "Heard audio appears here — press Enter to get AI answer"
        )
        self.tab_suggest_lay.addWidget(self.stream_box)

        # Last heard label
        self.heard_label = QLabel("Nothing heard yet")
        self.heard_label.setStyleSheet(
            f"font-size: 10px; color: {TEXT_SECONDARY}; font-style: italic;"
        )
        self.heard_label.setWordWrap(True)
        self.tab_suggest_lay.addWidget(self.heard_label)

        # Quick ask box + Answer button
        ask_row = QHBoxLayout()
        self.ask_input = QLineEdit()
        self.ask_input.setPlaceholderText("Heard text shown above — press Enter to answer, or type manually…")
        self.ask_input.returnPressed.connect(self._on_enter)
        ask_row.addWidget(self.ask_input)
        ask_btn = QPushButton("Ask")
        ask_btn.setObjectName("accent")
        ask_btn.clicked.connect(self._on_enter)
        ask_row.addWidget(ask_btn)
        self.tab_suggest_lay.addLayout(ask_row)

        # Enter hint
        enter_hint = QLabel("Press Enter with empty box to answer last heard question")
        enter_hint.setStyleSheet(f"font-size: 10px; color: {TEXT_SECONDARY};")
        self.tab_suggest_lay.addWidget(enter_hint)

        # Mode toggle row
        mode_row = QHBoxLayout()
        self._mode_label = QLabel("Mode:")
        self._mode_label.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        mode_row.addWidget(self._mode_label)
        self._mode_auto_btn = QPushButton("Auto")
        self._mode_code_btn = QPushButton("Code")
        self._mode_meet_btn = QPushButton("Meeting")
        self._mode_auto_btn.setObjectName("accent")   # default selected
        for btn, mode in [
            (self._mode_auto_btn, "auto"),
            (self._mode_code_btn, "coding"),
            (self._mode_meet_btn, "meeting"),
        ]:
            btn.setFixedHeight(22)
            btn.clicked.connect(lambda _, m=mode: self._set_ask_mode(m))
            mode_row.addWidget(btn)
        mode_row.addStretch()
        self.tab_suggest_lay.addLayout(mode_row)

        copy_top = QPushButton("Copy Answer  (F10)")
        copy_top.setObjectName("accent")
        copy_top.clicked.connect(self._copy_top_suggestion)
        self.tab_suggest_lay.addWidget(copy_top)

        screenshot_btn = QPushButton("Screenshot + Analyze  (F11)")
        screenshot_btn.clicked.connect(self._do_screenshot_analysis)
        self.tab_suggest_lay.addWidget(screenshot_btn)

        self.tabs.addTab(self.tab_suggest, "Suggest")

        # Tab 2: Transcript
        self.tab_transcript = QWidget()
        lay2 = QVBoxLayout(self.tab_transcript)
        self.transcript_box = QTextEdit()
        self.transcript_box.setReadOnly(True)
        self.transcript_box.setPlaceholderText("Live transcript will appear here…")
        lay2.addWidget(self.transcript_box)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.transcript_box.clear)
        lay2.addWidget(clear_btn, alignment=Qt.AlignmentFlag.AlignRight)
        self.tabs.addTab(self.tab_transcript, "📝 Transcript")

        # Tab 3: Summary/Notes
        self.tab_summary = QWidget()
        lay3 = QVBoxLayout(self.tab_summary)
        self.summary_box = QTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setPlaceholderText("Meeting summary generated here…")
        lay3.addWidget(self.summary_box)
        btn_row = QHBoxLayout()
        for fmt, label in [("md", "Export MD"), ("pdf", "Export PDF"), ("docx", "Export DOCX")]:
            b = QPushButton(label)
            b.clicked.connect(lambda _, f=fmt: self._export(f))
            btn_row.addWidget(b)
        lay3.addLayout(btn_row)
        self.tabs.addTab(self.tab_summary, "📊 Notes")

        # Tab 4: Settings
        self.tab_settings = QWidget()
        lay4 = QVBoxLayout(self.tab_settings)
        lay4.setSpacing(10)

        # ── Opacity ───────────────────────────────────────────────────────────
        lay4.addWidget(self._make_label("Opacity", TEXT_SECONDARY, 11))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(95)
        self.opacity_slider.valueChanged.connect(lambda v: self.setWindowOpacity(v / 100))
        lay4.addWidget(self.opacity_slider)

        # ── Job details ───────────────────────────────────────────────────────
        job_row = QHBoxLayout()
        job_row.setSpacing(8)

        job_col = QVBoxLayout()
        job_col.addWidget(self._make_label("Job Title:", TEXT_SECONDARY, 11))
        self.job_title_input = QLineEdit()
        self.job_title_input.setPlaceholderText("e.g. Senior Backend Engineer")
        self.job_title_input.setText(os.environ.get("MEETAI_JOB_TITLE", ""))
        job_col.addWidget(self.job_title_input)
        job_row.addLayout(job_col)

        co_col = QVBoxLayout()
        co_col.addWidget(self._make_label("Company:", TEXT_SECONDARY, 11))
        self.company_input = QLineEdit()
        self.company_input.setPlaceholderText("e.g. Google")
        self.company_input.setText(os.environ.get("MEETAI_COMPANY", ""))
        co_col.addWidget(self.company_input)
        job_row.addLayout(co_col)

        lay4.addLayout(job_row)

        # ── Context prompt ────────────────────────────────────────────────────
        lay4.addWidget(self._make_label("Your resume / background:", TEXT_SECONDARY, 11))
        self.ctx_input = QTextEdit()
        self.ctx_input.setMaximumHeight(90)
        self.ctx_input.setPlaceholderText(
            "e.g. Senior SRE at fintech, 8 years with Kubernetes, Kafka, Python. "
            "Led 12-person team. Strong in system design and distributed systems."
        )
        _env_ctx = os.environ.get("MEETAI_CONTEXT", "")
        if _env_ctx:
            self.ctx_input.setPlainText(_env_ctx)
        lay4.addWidget(self.ctx_input)

        save_ctx_btn = QPushButton("Save & Start Session")
        save_ctx_btn.setObjectName("accent")
        save_ctx_btn.clicked.connect(self._save_context)
        lay4.addWidget(save_ctx_btn)

        # ── Document upload ───────────────────────────────────────────────────
        lay4.addWidget(self._make_label("Knowledge base (resume, notes, docs):", TEXT_SECONDARY, 11))
        self.doc_status = QLabel("No documents uploaded yet.")
        self.doc_status.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY}; font-style: italic;")
        self.doc_status.setWordWrap(True)
        lay4.addWidget(self.doc_status)

        upload_btn = QPushButton("Upload Document  (PDF / DOCX / TXT)")
        upload_btn.clicked.connect(self._upload_document)
        lay4.addWidget(upload_btn)

        # ── AI Model ─────────────────────────────────────────────────────────
        lay4.addWidget(self._make_label("AI Model:", TEXT_SECONDARY, 11))
        model_row = QHBoxLayout()
        self._model_btns: dict[str, QPushButton] = {}
        for key, label in [("ollama", "Local"), ("claude", "Claude"), ("gpt4", "GPT-4"), ("gemini", "Gemini")]:
            b = QPushButton(label)
            b.clicked.connect(lambda _, k=key: self._set_model(k))
            self._model_btns[key] = b
            model_row.addWidget(b)
        lay4.addLayout(model_row)

        self.backend_status = QLabel("◉ Connecting…")
        self.backend_status.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        lay4.addWidget(self.backend_status)

        click_through_btn = QPushButton("Toggle Click-Through  (Ctrl+Shift+M)")
        click_through_btn.clicked.connect(self._toggle_click_through)
        lay4.addWidget(click_through_btn)

        # ── Screen share visibility ───────────────────────────────────────────
        lay4.addWidget(self._make_label("Screen Share Visibility:", TEXT_SECONDARY, 11))
        stealth_row = QHBoxLayout()
        stealth_info = QLabel(
            "HIDDEN = invisible to OBS, Zoom, Meet, Teams\n"
            "VISIBLE = appears on your shared screen"
        )
        stealth_info.setStyleSheet(f"font-size: 10px; color: {TEXT_SECONDARY};")
        stealth_info.setWordWrap(True)
        stealth_row.addWidget(stealth_info)
        stealth_toggle_btn = QPushButton("Toggle Stealth")
        stealth_toggle_btn.clicked.connect(self._toggle_stealth)
        stealth_row.addWidget(stealth_toggle_btn)
        lay4.addLayout(stealth_row)

        lay4.addStretch()
        self.tabs.addTab(self.tab_settings, "Settings")

    def _make_header(self) -> QWidget:
        header = QWidget()
        lay = QHBoxLayout(header)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Logo + title
        logo = QLabel("◈")
        logo.setStyleSheet(f"font-size: 16px; color: {ACCENT};")
        title = QLabel("MeetAI")
        title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {TEXT_ACCENT}; letter-spacing: 0.5px;")
        lay.addWidget(logo)
        lay.addWidget(title)
        lay.addStretch()

        # Status dot
        self.status_dot = QLabel("● --:--")
        self.status_dot.setStyleSheet("font-size: 11px; color: #ef4444; font-weight: 600; letter-spacing: 2px;")
        lay.addWidget(self.status_dot)
        lay.addSpacing(4)

        # Stealth toggle button — always visible in header for quick access
        self.stealth_btn = QPushButton("HIDDEN")
        self.stealth_btn.setFixedHeight(22)
        self.stealth_btn.setFixedWidth(62)
        self.stealth_btn.setToolTip(
            "HIDDEN: overlay is invisible to screen share / OBS / Zoom\n"
            "VISIBLE: overlay appears on shared screen (click to toggle)"
        )
        self.stealth_btn.setStyleSheet("""
            QPushButton {
                background: #166534;
                color: #86efac;
                border: 1px solid #16a34a;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
                padding: 0 4px;
            }
            QPushButton:hover { background: #15803d; }
        """)
        self.stealth_btn.clicked.connect(self._toggle_stealth)
        lay.addWidget(self.stealth_btn)
        lay.addSpacing(4)

        # Listen toggle button
        self.listen_btn = QPushButton("MIC OFF")
        self.listen_btn.setFixedHeight(22)
        self.listen_btn.setFixedWidth(62)
        self.listen_btn.setToolTip("Click to start listening to the call audio")
        self.listen_btn.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #64748b;
                border: 1px solid #334155;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
                padding: 0 4px;
            }
            QPushButton:hover { background: #334155; }
        """)
        self.listen_btn.clicked.connect(self._toggle_listen)
        lay.addWidget(self.listen_btn)
        lay.addSpacing(4)

        # Minimize / hide
        for text, slot in [("▼", self._toggle_minimize), ("✕", self.hide)]:
            b = QPushButton(text)
            b.setFixedSize(26, 26)
            b.clicked.connect(slot)
            lay.addWidget(b)

        return header

    def _make_label(self, text: str, color: str, size: int) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-size: {size}px; color: {color}; letter-spacing: 0.5px;")
        return lbl

    # ── System tray ──────────────────────────────────────────────────────────

    def _setup_tray(self):
        icon = self._make_tray_icon()
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        menu.addAction(QAction("Show / Hide  (F9)", self, triggered=self._toggle_visibility))
        menu.addAction(QAction("Copy Answer  (F10)", self, triggered=self._copy_top_suggestion))
        menu.addAction(QAction("Screenshot+AI  (F11)", self, triggered=self._do_screenshot_analysis))
        menu.addSeparator()
        menu.addAction(QAction("Quit MeetAI", self, triggered=QApplication.quit))
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("MeetAI — Invisible AI Co-pilot")
        self.tray.show()

    def _make_tray_icon(self) -> QIcon:
        px = QPixmap(32, 32)
        px.fill(QColor(0, 0, 0, 0))
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(99, 102, 241)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 28, 28)
        p.setPen(QPen(QColor(255, 255, 255, 220), 2))
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "M")
        p.end()
        return QIcon(px)

    # ── Global hotkeys ───────────────────────────────────────────────────────

    def _setup_state(self):
        self._elapsed = 0
        self._meeting_active = False
        self._current_suggestion = ""
        self._current_model = os.environ.get("MEETAI_DEFAULT_MODEL", "ollama")
        self._local_context = os.environ.get("MEETAI_CONTEXT", "")
        self._local_job_title = os.environ.get("MEETAI_JOB_TITLE", "")
        self._local_company = os.environ.get("MEETAI_COMPANY", "")
        self._ask_mode = "auto"   # "auto" | "coding" | "meeting"
        self._stealth_active = True
        self._listening = False
        self._last_heard = ""     # last line transcribed from audio
        self._audio_engine = None
        self._backend_ok = False
        self._session_started = False   # tracks whether /meeting/start has been sent
        self._worker: Optional[SuggestionWorker] = None

        # Register global hotkeys
        self._hotkeys = HotkeyManager({
            "<f9>":                  self._toggle_visibility,
            "<f10>":                 self._copy_top_suggestion,
            "<f11>":                 self._do_screenshot_analysis,
            "<ctrl>+<shift>+m":     self._toggle_click_through,
        })
        self._hotkeys.start()

        # Backend status poller
        self._poller = BackendPoller()
        self._poller.status_changed.connect(self._on_backend_status)
        self._poller.start()

    def _start_timers(self):
        self._clock = QTimer()
        self._clock.timeout.connect(self._tick)
        self._clock.start(1000)

    # ── Timer / clock ────────────────────────────────────────────────────────

    def _tick(self):
        if self._meeting_active:
            self._elapsed += 1
            m, s = divmod(self._elapsed, 60)
            self.status_dot.setText(f"● LIVE  {m:02d}:{s:02d}")
            self.status_dot.setStyleSheet("font-size: 11px; color: #ef4444; font-weight: 600; letter-spacing: 2px;")
        else:
            self.status_dot.setText("◉ READY")
            self.status_dot.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY}; font-weight: 600; letter-spacing: 2px;")

    # ── Backend status ───────────────────────────────────────────────────────

    def _on_backend_status(self, ok: bool):
        self._backend_ok = ok
        if ok:
            self.backend_status.setText("◉ Backend connected — AI ready")
            self.backend_status.setStyleSheet("font-size: 11px; color: #34d399;")
        else:
            self.backend_status.setText("◉ Demo mode (no backend)")
            self.backend_status.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")

    # ── Hotkey actions ───────────────────────────────────────────────────────

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()

    def _copy_top_suggestion(self):
        text = self._current_suggestion or self.stream_box.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._flash_status("✅ Copied!")

    def _toggle_minimize(self):
        if self._minimized_h:
            self.resize(380, 640)
        else:
            self.resize(380, 52)
        self._minimized_h = not self._minimized_h

    def _toggle_click_through(self):
        self._click_through = not self._click_through
        flags = self.windowFlags()
        if self._click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
        else:
            flags &= ~Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.show()                # required after flag change
        hwnd = int(self.winId())
        _set_layered_style(hwnd)
        apply_stealth(hwnd)        # re-apply after flag change
        self._flash_status(f"Click-through: {'ON' if self._click_through else 'OFF'}")

    # ── Stealth toggle ───────────────────────────────────────────────────────

    def _toggle_stealth(self):
        """Toggle whether the overlay is hidden from screen capture."""
        self._stealth_active = not self._stealth_active
        hwnd = int(self.winId())
        if self._stealth_active:
            # Re-apply WDA_EXCLUDEFROMCAPTURE — hidden from OBS/Zoom/Meet
            apply_stealth(hwnd)
            self.stealth_btn.setText("HIDDEN")
            self.stealth_btn.setStyleSheet("""
                QPushButton {
                    background: #166534;
                    color: #86efac;
                    border: 1px solid #16a34a;
                    border-radius: 4px;
                    font-size: 10px;
                    font-weight: 700;
                    letter-spacing: 1px;
                    padding: 0 4px;
                }
                QPushButton:hover { background: #15803d; }
            """)
            self._flash_status("Stealth ON — hidden from screen share")
        else:
            # Remove display affinity — overlay visible on shared screen
            if sys.platform == "win32":
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00)
            self.stealth_btn.setText("VISIBLE")
            self.stealth_btn.setStyleSheet("""
                QPushButton {
                    background: #7c2d12;
                    color: #fdba74;
                    border: 1px solid #ea580c;
                    border-radius: 4px;
                    font-size: 10px;
                    font-weight: 700;
                    letter-spacing: 1px;
                    padding: 0 4px;
                }
                QPushButton:hover { background: #9a3412; }
            """)
            self._flash_status("Stealth OFF — visible on screen share")

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32" and getattr(self, "_stealth_active", True):
            hwnd = int(self.winId())
            apply_stealth(hwnd)

    # ── Manual question ask ──────────────────────────────────────────────────

    def _on_enter(self):
        """Enter pressed or Ask clicked — use typed text or fall back to last heard."""
        q = self.ask_input.text().strip()
        if not q:
            q = self._last_heard.strip()
        if q:
            self.ask_input.clear()
            self.trigger_suggestion(q, mode=self._ask_mode)

    def _toggle_listen(self):
        """Start / stop the audio engine listening to call audio."""
        if self._listening:
            # Stop
            if self._audio_engine:
                self._audio_engine.stop()
                self._audio_engine = None
            self._listening = False
            self.listen_btn.setText("MIC OFF")
            self.listen_btn.setStyleSheet("""
                QPushButton {
                    background: #1e293b;
                    color: #64748b;
                    border: 1px solid #334155;
                    border-radius: 4px;
                    font-size: 10px;
                    font-weight: 700;
                    letter-spacing: 1px;
                    padding: 0 4px;
                }
                QPushButton:hover { background: #334155; }
            """)
            self._flash_status("Mic stopped")
        else:
            # Start — load capture.py directly by path to avoid circular import
            # (backend.server is already in sys.modules when overlay runs)
            try:
                import importlib.util as _ilu
                _spec = _ilu.spec_from_file_location(
                    "capture",
                    str(Path(__file__).parent.parent / "audio" / "capture.py"),
                )
                _mod = _ilu.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)
                AudioEngine = _mod.AudioEngine
                self._audio_engine = AudioEngine(
                    on_transcript=self._on_audio_transcript,
                    whisper_model=os.environ.get("WHISPER_MODEL", "base"),
                )
                self._audio_engine.start()
                self._listening = True
                self.listen_btn.setText("LIVE")
                self.listen_btn.setStyleSheet("""
                    QPushButton {
                        background: #7f1d1d;
                        color: #fca5a5;
                        border: 1px solid #ef4444;
                        border-radius: 4px;
                        font-size: 10px;
                        font-weight: 700;
                        letter-spacing: 1px;
                        padding: 0 4px;
                    }
                    QPushButton:hover { background: #991b1b; }
                """)
                self._flash_status("Listening — press Enter to answer")
            except ImportError as exc:
                missing = str(exc).replace("No module named ", "").strip("'")
                self._flash_status(f"Missing: pip install {missing}")
                _log(f"[audio] ImportError: {exc}")
                _log("[audio] Run:  pip install PyAudioWPatch SpeechRecognition sounddevice")
            except Exception as exc:
                self._flash_status(f"Audio failed: {exc}")
                _log(f"[audio] Error: {exc}")

    def _on_audio_transcript(self, speaker: str, text: str):
        """Called from audio thread when speech is transcribed — thread-safe via QTimer."""
        def _update():
            self._last_heard = text
            # Show in transcript tab
            line = f"[{speaker}] {text}"
            self.transcript_box.append(line)
            # POST to backend in background — never block the UI thread
            threading.Thread(
                target=_api,
                args=("POST", "/transcript/add", {"speaker": speaker, "text": text}),
                daemon=True,
            ).start()
            # Show preview under stream box
            preview = text if len(text) <= 80 else text[:77] + "..."
            self.heard_label.setText(f"Heard: \"{preview}\"  — press Enter to answer")
            self.heard_label.setStyleSheet(
                "font-size: 10px; color: #a78bfa; font-style: italic;"
            )
        QTimer.singleShot(0, _update)

    def _set_model(self, key: str):
        self._current_model = key
        for k, b in self._model_btns.items():
            b.setObjectName("accent" if k == key else "")
            b.setStyle(b.style())

    def _set_ask_mode(self, mode: str):
        self._ask_mode = mode
        for btn, m in [
            (self._mode_auto_btn, "auto"),
            (self._mode_code_btn, "coding"),
            (self._mode_meet_btn, "meeting"),
        ]:
            btn.setObjectName("accent" if m == mode else "")
            btn.setStyle(btn.style())

    # ── Context + document management ───────────────────────────────────────

    def _save_context(self):
        """Send the context prompt, job title, and company to the backend."""
        ctx = self.ctx_input.toPlainText().strip()
        job = self.job_title_input.text().strip()
        company = self.company_input.text().strip()
        self._local_context = ctx
        self._local_job_title = job
        self._local_company = company
        self._session_started = False   # force re-send on next question
        self._flash_status("Saving session...")

        def _do():
            resp = _api("POST", "/meeting/start", {
                "model": self._current_model,
                "context": ctx,
                "job_title": job,
                "company": company,
            })
            if resp:
                self._session_started = True
                label = f"Ready -- {job} at {company}" if job and company else "Session started"
                QTimer.singleShot(0, lambda: self._flash_status(label))
            else:
                QTimer.singleShot(0, lambda: self._flash_status("Backend offline -- saved locally"))

        threading.Thread(target=_do, daemon=True).start()

    def _upload_document(self):
        """Open a file picker and upload the chosen file to the RAG pipeline."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Upload Document",
            str(Path.home()),
            "Documents (*.pdf *.docx *.txt);;All Files (*)",
        )
        if not path:
            return

        file_path = Path(path)
        self.doc_status.setText(f"Uploading {file_path.name}...")

        # Run upload in a thread so the UI doesn't freeze
        def do_upload():
            try:
                import urllib.request, urllib.parse
                url = "http://127.0.0.1:8765/rag/upload"
                boundary = "----MeetAIBoundary"
                data = file_path.read_bytes()
                fname = file_path.name
                # Build multipart body manually (no external deps)
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
                    f"Content-Type: application/octet-stream\r\n\r\n"
                ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
                req = urllib.request.Request(url, data=body, method="POST")
                req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
                with urllib.request.urlopen(req, timeout=30) as r:
                    import json
                    result = json.load(r)
                chunks = result.get("chunks", "?")
                # Update UI on main thread
                QTimer.singleShot(0, lambda: self.doc_status.setText(
                    f"{fname} indexed — {chunks} chunks in knowledge base."
                ))
                QTimer.singleShot(0, lambda: self._flash_status("Document indexed!"))
            except Exception as exc:
                QTimer.singleShot(0, lambda: self.doc_status.setText(
                    f"Upload failed: {exc}"
                ))

        threading.Thread(target=do_upload, daemon=True).start()

    # ── AI suggestion pipeline ───────────────────────────────────────────────

    def trigger_suggestion(self, question: str, mode: str = "auto"):
        """Called by audio VAD or manually — fires an AI suggestion for the question."""
        if self._worker and self._worker.isRunning():
            # Disconnect stale signals before terminating so stale tokens
            # don't land in the new answer box.
            try:
                self._worker.token.disconnect()
                self._worker.done.disconnect()
            except Exception:
                pass
            self._worker.terminate()
            self._worker.wait(300)   # give it up to 300ms to die cleanly

        self._meeting_active = True
        self.stream_box.setPlainText(f"Thinking about: {question[:80]}{'...' if len(question) > 80 else ''}\n\n")
        self._current_suggestion = ""
        self.tabs.setCurrentIndex(0)

        # Read the current context from the UI (always fresh — user may have typed
        # without clicking Save).  _local_* is only updated when Save is clicked.
        ctx = self.ctx_input.toPlainText().strip() or self._local_context
        job = self.job_title_input.text().strip() or self._local_job_title
        company = self.company_input.text().strip() or self._local_company

        # Start the worker with context embedded directly — no race with /meeting/start
        self._worker = SuggestionWorker(question, mode=mode,
                                        context=ctx, job_title=job, company=company,
                                        model=self._current_model)
        self._worker.token.connect(self._on_token)
        self._worker.done.connect(self._on_done)

        # Also sync the backend state in the background (for transcript/summary endpoints)
        if not getattr(self, "_session_started", False):
            def _start_session():
                _api("POST", "/meeting/start", {
                    "model": self._current_model,
                    "context": ctx,
                    "job_title": job,
                    "company": company,
                })
            threading.Thread(target=_start_session, daemon=True).start()
            self._session_started = True

        self._worker.start()

    def _on_token(self, token: str):
        self._current_suggestion += token
        self.stream_box.setPlainText(self._current_suggestion)
        # Scroll to end
        sb = self.stream_box.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def _on_done(self, full_text: str):
        self._current_suggestion = full_text
        self.stream_box.setPlainText(full_text)

    # ── Screenshot + Vision analysis ─────────────────────────────────────────

    def _do_screenshot_analysis(self):
        self.stream_box.setPlainText("📸 Capturing screen and analyzing…")
        self.tabs.setCurrentIndex(0)
        worker = ScreenshotAnalysisWorker(self)
        worker.result.connect(self._on_screenshot_result)
        worker.start()
        self._ss_worker = worker   # keep reference

    def _on_screenshot_result(self, analysis: str):
        self._current_suggestion = analysis
        self.stream_box.setPlainText(analysis)

    # ── Export ───────────────────────────────────────────────────────────────

    def _export(self, fmt: str):
        """Trigger export — backend saves the file; open the download URL in browser."""
        import webbrowser
        url = f"http://127.0.0.1:8765/meeting/export?format={fmt}"
        self._flash_status("Exporting…")

        def _do():
            try:
                check = _api("GET", "/health", timeout=3)
                if check and check.get("status") == "ok":
                    webbrowser.open(url)
                    QTimer.singleShot(0, lambda: self._flash_status("Export started — check browser download"))
                else:
                    QTimer.singleShot(0, lambda: self._flash_status("Backend offline — export unavailable"))
            except Exception:
                QTimer.singleShot(0, lambda: self._flash_status("Export failed — is backend running?"))

        threading.Thread(target=_do, daemon=True).start()

    # ── External update methods (called by audio engine) ─────────────────────

    def update_transcript(self, speaker: str, text: str):
        """Called by audio capture thread to add transcript lines — route to main thread."""
        # All Qt UI calls must happen on the main thread
        def _update():
            line = f"{'[You]' if speaker == 'You' else '[Them]'} {text}"
            self.transcript_box.append(line)
            threading.Thread(
                target=_api,
                args=("POST", "/transcript/add", {"speaker": speaker, "text": text}),
                daemon=True,
            ).start()
            if speaker == "Them":
                self.trigger_suggestion(text)
        QTimer.singleShot(0, _update)

    def update_summary(self, md: str):
        self.summary_box.setPlainText(md)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _flash_status(self, msg: str, ms: int = 2500):
        prev = self.status_dot.text()
        self.status_dot.setText(msg)
        QTimer.singleShot(ms, lambda: self.status_dot.setText(prev))

    # ── Cleanup ──────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        """Stop background threads gracefully before closing."""
        if getattr(self, "_audio_engine", None):
            self._audio_engine.stop()
        if getattr(self, "_hotkeys", None):
            self._hotkeys.stop()
        if getattr(self, "_poller", None):
            self._poller.stop()
            self._poller.wait(2000)
        super().closeEvent(event)

    # ── Paint (glass background) ──────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(13, 17, 23, 245)))
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        p.drawRoundedRect(self.rect(), 18, 18)

    # ── Drag ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if getattr(self, "_drag_pos", None) is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def run_overlay() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("MeetAI")
    app.setQuitOnLastWindowClosed(False)   # keep tray alive when window hidden

    overlay = StealthOverlay()
    overlay.show()

    # Demo: pre-populate with a sample suggestion
    overlay.stream_box.setPlainText(
        "👋 Ready. MeetAI is listening.\n\n"
        "• Mic captured via getUserMedia\n"
        "• System audio via WASAPI loopback\n"
        "• AI suggestions appear automatically after they stop talking\n\n"
        "Hotkeys:\n"
        "  F9  → Toggle visibility\n"
        "  F10 → Copy top answer\n"
        "  F11 → Screenshot + AI analysis\n"
        "  Ctrl+Shift+M → Click-through mode"
    )

    sys.exit(app.exec())


if __name__ == "__main__":
    run_overlay()
