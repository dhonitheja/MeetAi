import os
import pytest
import hmac
import hashlib

os.environ["RECALL_WEBHOOK_SECRET"] = "test-webhook-secret"

from backend.meeting.transcript_handler import TranscriptHandler, TranscriptLine


def make_event(speaker="Alice", text="How does the API work?", bot_id="bot123"):
    return {
        "event": "transcript.data",
        "data": {
            "bot_id": bot_id,
            "transcript": {
                "speaker": speaker,
                "words": [{"text": word} for word in text.split()],
            },
        },
    }


def test_process_event_returns_line():
    handler = TranscriptHandler()
    line = handler.process_event(make_event())
    assert isinstance(line, TranscriptLine)
    assert line.speaker == "Alice"
    assert "API" in line.text


def test_unknown_event_returns_none():
    handler = TranscriptHandler()
    result = handler.process_event({"event": "bot.joined", "data": {}})
    assert result is None


def test_sanitize_removes_control_chars():
    handler = TranscriptHandler()
    line = handler.process_event(make_event(text="Hello\x00World"))
    assert line is not None
    assert "\x00" not in line.text


def test_hmac_valid_signature():
    handler = TranscriptHandler()
    payload = b'{"event":"transcript.data"}'
    sig = hmac.new(b"test-webhook-secret", payload, hashlib.sha256).hexdigest()
    assert handler.verify_webhook_signature(payload, sig)


def test_hmac_invalid_signature_rejected():
    handler = TranscriptHandler()
    payload = b'{"event":"transcript.data"}'
    assert not handler.verify_webhook_signature(payload, "fakesignature")


def test_missing_webhook_secret_returns_false(monkeypatch):
    monkeypatch.delenv("RECALL_WEBHOOK_SECRET", raising=False)
    handler = TranscriptHandler()
    assert not handler.verify_webhook_signature(b"payload", "sig")


def test_thread_safety():
    import threading

    handler = TranscriptHandler()
    errors = []

    def add_lines():
        for i in range(50):
            try:
                handler.process_event(make_event(text=f"Line {i}"))
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=add_lines) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
