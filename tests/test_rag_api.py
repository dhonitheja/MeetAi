import os

from fastapi.testclient import TestClient

os.environ.setdefault("PERSONA_MACHINE_ID", "test")
os.environ.setdefault("PERSONA_USER_SALT", "test-salt")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("RECALL_API_KEY", "test-recall-key")
os.environ.setdefault("RECALL_WEBHOOK_SECRET", "test-recall-secret")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_abc123")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_abc123")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_pro_test")
os.environ.setdefault("STRIPE_TEAM_PRICE_ID", "price_team_test")
os.environ.setdefault("APP_BASE_URL", "http://localhost:8765")

from server import app
from unittest.mock import MagicMock
from backend.routers.rag import get_store

mock_store = MagicMock()
mock_store.list_documents.return_value = []
mock_store.delete_document.return_value = 0
mock_store.query.return_value = []

app.dependency_overrides[get_store] = lambda: mock_store

client = TestClient(app)


def test_list_files_returns_list():
    res = client.get("/rag/files")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_upload_wrong_extension_rejected():
    res = client.post(
        "/rag/upload",
        files=[("file", ("malware.exe", b"MZ\x90\x00", "application/pdf"))],
    )
    assert res.status_code == 400


def test_upload_bad_magic_bytes_rejected():
    # PDF extension but not PDF content
    res = client.post(
        "/rag/upload",
        files=[("file", ("fake.pdf", b"not a pdf at all", "application/pdf"))],
    )
    assert res.status_code == 400


def test_upload_oversized_rejected():
    big = b"%PDF" + b"x" * (20 * 1024 * 1024 + 1)
    res = client.post(
        "/rag/upload",
        files=[("file", ("big.pdf", big, "application/pdf"))],
    )
    assert res.status_code == 413


def test_delete_nonexistent_returns_404():
    res = client.delete("/rag/file/doesnotexist.pdf")
    assert res.status_code == 404


def test_query_empty_returns_empty():
    res = client.post("/rag/query?text=what+is+the+deadline")
    assert res.status_code == 200
    assert "results" in res.json()
