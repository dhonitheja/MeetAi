"""
MeetAI - run from anywhere
  python run.py
"""
import sys
import os
from pathlib import Path

# Ensure project root is on sys.path regardless of cwd
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)  # also set cwd so .env is found

import uvicorn
uvicorn.run("backend.server:app", host="127.0.0.1", port=8765, log_level="info")
