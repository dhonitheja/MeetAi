# -*- mode: python ; coding: utf-8 -*-
"""
MeetAI PyInstaller Spec
========================
Builds a single-folder distribution (onedir mode) so Whisper models
can be downloaded at runtime without bloating the installer.

Build:
    pip install pyinstaller
    pyinstaller packaging/meetai.spec

Output: dist/MeetAI/MeetAI.exe  (Windows)
        dist/MeetAI/MeetAI      (macOS/Linux)
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent   # noqa: F821 — PyInstaller globals

a = Analysis(
    [str(ROOT / "start.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Include backend Python package
        (str(ROOT / "backend"), "backend"),
        # Include .env.example so users know what to fill in
        (str(ROOT / ".env.example"), "."),
        # Include any local model weights if pre-downloaded
        # (str(ROOT / "models"), "models"),
    ],
    hiddenimports=[
        # PyQt6
        "PyQt6", "PyQt6.QtWidgets", "PyQt6.QtCore", "PyQt6.QtGui",
        # Audio
        "sounddevice", "pyaudiowpatch",
        # ML
        "torch", "torch.hub",
        "faster_whisper",
        "sentence_transformers",
        # Chromadb
        "chromadb",
        "chromadb.api", "chromadb.api.models",
        # LiteLLM
        "litellm",
        # FastAPI / uvicorn
        "fastapi", "uvicorn", "uvicorn.main", "uvicorn.config",
        "starlette", "anyio",
        # Utils
        "pynput", "pynput.keyboard", "pynput.mouse",
        "PIL", "PIL.ImageGrab",
        "setproctitle",
        "dotenv",
        "fpdf",
        "pypdf",
        "docx",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "jupyter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)   # noqa: F821

exe = EXE(   # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MeetAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # no console window on Windows
    icon=str(ROOT / "public" / "icon.ico") if (ROOT / "public" / "icon.ico").exists() else None,
    # On Windows: process name shown in Task Manager = "MeetAI"
    # but we rename it at runtime via setproctitle
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="MeetAI",
)

# macOS: bundle as .app
if sys.platform == "darwin":
    app = BUNDLE(   # noqa: F821
        coll,
        name="MeetAI.app",
        icon=str(ROOT / "public" / "icon.icns") if (ROOT / "public" / "icon.icns").exists() else None,
        bundle_identifier="app.meetai.assistant",
        info_plist={
            "NSMicrophoneUsageDescription": "MeetAI needs microphone access to transcribe your side of the conversation.",
            "NSScreenCaptureUsageDescription": "MeetAI captures system audio to transcribe the other speaker.",
            "NSBluetoothAlwaysUsageDescription": "",
        },
    )
