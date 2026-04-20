"""
MeetAI — one command launcher
  python start.py
"""
import os
import sys
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# ── Load .env ────────────────────────────────────────────────────────────────

def _load_env():
    env = ROOT / ".env"
    if not env.exists():
        example = ROOT / ".env.example"
        if example.exists():
            import shutil
            shutil.copy(example, env)
            print("[start] .env not found — copied from .env.example")
    try:
        from dotenv import load_dotenv
        load_dotenv(env)
    except ImportError:
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

# ── Start backend ─────────────────────────────────────────────────────────────

def _start_backend():
    print("[start] Starting backend on http://127.0.0.1:8765 ...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.server:app",
         "--host", "127.0.0.1", "--port", "8765", "--log-level", "warning"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Poll until healthy (up to 30s)
    ready = False
    for _ in range(60):
        try:
            urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=1)
            ready = True
            break
        except Exception:
            time.sleep(0.5)
    if ready:
        print("[start] Backend ready")
    else:
        print("[start] Backend slow to start — overlay runs in demo mode")
    return proc

backend_proc = None

def _backend_thread():
    global backend_proc
    backend_proc = _start_backend()

t = threading.Thread(target=_backend_thread, daemon=True)
t.start()

# Give backend a moment before Qt starts
time.sleep(1.5)

# ── Launch Qt overlay ─────────────────────────────────────────────────────────

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("[start] ERROR: PyQt6 not installed. Run:  pip install PyQt6")
        sys.exit(1)

from backend.ui.overlay import StealthOverlay

app = QApplication(sys.argv)
app.setApplicationName("MeetAI")
app.setQuitOnLastWindowClosed(False)

overlay = StealthOverlay()
overlay.show()

print("[start] MeetAI running")
print("[start] Hotkeys: F9=show/hide  F10=copy answer  F11=screenshot  Ctrl+Shift+M=click-through")
print("[start] Backend docs: http://127.0.0.1:8765/docs")

exit_code = app.exec()

if backend_proc:
    backend_proc.terminate()

sys.exit(exit_code)
