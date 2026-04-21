"""
Rolling Meeting Summary + Action Item Extractor
================================================
Uses a sliding-window pattern:
  1. Accumulate recent transcript (up to BUFFER_WORDS words)
  2. When buffer fills, compress into running_summary via LLM
  3. Repeat — running_summary stays bounded, recent detail stays verbatim

Action items extracted in structured JSON for export.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

# Load .env so OLLAMA_* vars are available when used standalone
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

try:
    import openai as _openai_sdk
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import anthropic as _ant
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

HAS_LLM = HAS_OPENAI or HAS_ANTHROPIC or HAS_GEMINI

BUFFER_WORDS = 500          # ~2-3 minutes of speech
MAX_SUMMARY_TOKENS = 600

_ollama_model = os.environ.get("OLLAMA_MODEL", "gemma3:1b")

MODEL_MAP = {
    "claude":  "claude-3-5-sonnet-20241022",
    "gpt4":    "gpt-4o",
    "gemini":  "gemini-2.0-flash-exp",
    "ollama":  _ollama_model,
}


def _llm_complete(model_key: str, prompt: str, max_tokens: int) -> str:
    """Route a completion request to the right provider."""
    if not HAS_LLM:
        raise RuntimeError("No LLM SDKs installed")

    model_name = MODEL_MAP.get(model_key, MODEL_MAP["ollama"])

    # 1. Google Gemini
    if model_key == "gemini":
        if not HAS_GEMINI: raise RuntimeError("google-generativeai not installed")
        api_key = os.environ.get("GEMINI_API_KEY", "")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        resp = model.generate_content(prompt, generation_config={"max_output_tokens": max_tokens})
        return resp.text

    # 2. Anthropic Claude
    if model_key == "claude":
        if not HAS_ANTHROPIC: raise RuntimeError("anthropic not installed")
        client = _ant.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        resp = client.messages.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return resp.content[0].text

    # 3. OpenAI or Ollama
    if not HAS_OPENAI: raise RuntimeError("openai not installed")
    if model_key == "ollama":
        base = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
        client = _openai_sdk.OpenAI(base_url=f"{base}/v1", api_key="ollama")
    else:
        client = _openai_sdk.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

    resp = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content

COMPRESS_PROMPT = """\
You are taking real-time meeting notes.

Existing summary:
{running_summary}

New transcript segment to incorporate:
{new_segment}

Produce a concise updated summary in markdown:

## Key Discussion Points
- (bullet each main topic)

## Action Items
- [ ] Owner: Task description  (add owner name in parentheses if mentioned)

## Decisions Made
- (bullet each decision)

## Open Questions
- (bullet unresolved questions)

Keep it tight — max 400 words total.
"""

ACTION_ITEM_PROMPT = """\
Extract all action items from this meeting notes text.

Notes:
{notes}

Return JSON only:
{{
  "action_items": [
    {{"task": "...", "owner": "...", "due": "...", "priority": "high|medium|low"}},
    ...
  ]
}}

If no owner is mentioned, use "TBD". If no due date, use "unspecified".
"""


class RollingSummarizer:
    def __init__(self, model: str = "ollama"):
        self.model = model
        self.running_summary: str = ""
        self._buffer: list[str] = []
        self._buffer_word_count = 0
        self._action_items: list[dict] = []

    def add_segment(self, speaker: str, text: str) -> Optional[str]:
        """
        Add a transcript segment. Returns updated summary if compression happened, else None.
        """
        line = f"{speaker}: {text}"
        self._buffer.append(line)
        self._buffer_word_count += len(text.split())

        if self._buffer_word_count >= BUFFER_WORDS:
            return self._compress()
        return None

    def _compress(self) -> str:
        new_segment = "\n".join(self._buffer)
        self._buffer = []
        self._buffer_word_count = 0

        if not HAS_LLM:
            self.running_summary += f"\n\n[{time.strftime('%H:%M')}] " + new_segment[:300] + "…"
            return self.running_summary

        try:
            prompt = COMPRESS_PROMPT.format(
                running_summary=self.running_summary or "(none yet)",
                new_segment=new_segment,
            )
            self.running_summary = _llm_complete(self.model, prompt, MAX_SUMMARY_TOKENS)
        except Exception as exc:
            print(f"[summarizer] compress failed: {exc}")
            self.running_summary += f"\n\n---\n{new_segment[:400]}"

        return self.running_summary

    def get_full_summary(self) -> str:
        """Force-compress remaining buffer and return complete notes."""
        if self._buffer:
            self._compress()
        return self.running_summary or "No meeting content recorded yet."

    def extract_action_items(self) -> list[dict]:
        """Extract structured action items from the running summary."""
        notes = self.get_full_summary()
        if not HAS_LLM:
            return self._parse_checkboxes(notes)

        try:
            prompt = ACTION_ITEM_PROMPT.format(notes=notes)
            raw = _llm_complete(self.model, prompt, 400)
            data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
            self._action_items = data.get("action_items", [])
        except Exception:
            self._action_items = self._parse_checkboxes(notes)

        return self._action_items

    def _parse_checkboxes(self, text: str) -> list[dict]:
        """Regex fallback: extract markdown checkboxes as action items."""
        items = []
        for match in re.finditer(r"-\s*\[\s*\]\s*(.+)", text):
            task = match.group(1).strip()
            # Try to extract owner from parentheses
            owner_match = re.search(r"\(([^)]+)\)", task)
            owner = owner_match.group(1) if owner_match else "TBD"
            items.append({"task": task, "owner": owner, "due": "unspecified", "priority": "medium"})
        return items

    def reset(self):
        self.running_summary = ""
        self._buffer = []
        self._buffer_word_count = 0
        self._action_items = []
