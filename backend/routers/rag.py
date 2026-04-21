from __future__ import annotations

import hashlib
import logging
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from backend.rag.document_store import DocumentStore

logger = logging.getLogger(__name__)

rag_router = APIRouter(prefix="/rag", tags=["rag"])

_store: DocumentStore | None = None

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
PDF_MAGIC = b"%PDF"
DOCX_MAGIC = b"PK\x03\x04"  # ZIP-based format
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def get_store() -> DocumentStore:
    if _store is None:
        raise HTTPException(503, "Document store not loaded")
    return _store


def _sanitize_collection_id(name: str) -> str:
    """
    Strip non-alphanumeric characters from document names used as identifiers.
    Prevents path traversal in ChromaDB queries.
    """
    clean = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return clean[:128]


def _validate_file_magic(data: bytes, filename: str) -> bool:
    """
    Validate file magic bytes match declared extension.
    Rejects executables renamed as PDF/DOCX.
    """
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return data[:4] == PDF_MAGIC
    if ext == ".docx":
        return data[:4] == DOCX_MAGIC
    return False


class DocumentResponse(BaseModel):
    source: str
    chunks: int


class QueryResponse(BaseModel):
    results: list[dict]


@rag_router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    store: DocumentStore = Depends(get_store),
):
    """
    Upload and ingest a PDF or DOCX document into the vector store.
    Validates MIME type, magic bytes, and file size.
    Saves to a temp file for parsing - temp file deleted after ingest.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Only PDF and DOCX files accepted. Got: {ext}")

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(400, f"Invalid content type: {file.content_type}")

    data = await file.read(MAX_FILE_SIZE + 1)
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large. Maximum size is 20MB.")

    if not _validate_file_magic(data, file.filename or ""):
        raise HTTPException(400, "File content does not match declared type. Upload rejected.")

    doc_hash = hashlib.sha256(data).hexdigest()
    suffix = ext
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)

        chunks_added = store.add_document(
            file_path=tmp_path,
            metadata={
                "original_filename": _sanitize_collection_id(file.filename or "upload"),
                "upload_sha256": doc_hash,
            },
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(422, str(e)) from e
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()

    return DocumentResponse(source=file.filename or "upload", chunks=chunks_added)


@rag_router.get("/files", response_model=list[DocumentResponse])
async def list_files(store: DocumentStore = Depends(get_store)):
    """List all indexed documents in the vector store."""
    docs = store.list_documents()
    return [DocumentResponse.model_validate(doc) for doc in docs]


@rag_router.delete("/file/{source_name}")
async def delete_file(
    source_name: str,
    store: DocumentStore = Depends(get_store),
):
    """Delete all chunks for a given source document."""
    deleted = store.delete_document(source_name)
    if deleted == 0:
        raise HTTPException(404, f"Document not found: {source_name}")
    return {"status": "deleted", "chunks_removed": deleted}


@rag_router.post("/query", response_model=QueryResponse)
async def query_documents(
    text: str = Query(..., min_length=1, max_length=500),
    n_results: int = Query(default=3, ge=1, le=10),
    store: DocumentStore = Depends(get_store),
):
    """Query the vector store for relevant document chunks."""
    results = store.query(text=text, n_results=n_results)
    return QueryResponse(results=results)


@rag_router.post("/cleanup")
async def cleanup(
    keep_latest: int = Query(default=20, ge=1, le=100),
    store: DocumentStore = Depends(get_store),
):
    """[VC-04] Remove oldest documents beyond keep_latest limit."""
    deleted = store.cleanup_old_documents(keep_latest=keep_latest)
    return {"status": "ok", "chunks_deleted": deleted}
