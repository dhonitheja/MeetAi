from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Any

try:
    import chromadb
    from chromadb.config import Settings
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
    from sentence_transformers import SentenceTransformer

    HAS_VECTOR_DEPS = True
except ImportError:
    chromadb = None
    Settings = None
    RecursiveCharacterTextSplitter = None
    Docx2txtLoader = None
    PyPDFLoader = None
    SentenceTransformer = None
    HAS_VECTOR_DEPS = False

logger = logging.getLogger(__name__)

CHROMA_DIR = Path("./data/chroma")
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION_NAME = "meetai_docs"
CHUNK_SIZE = 600
CHUNK_OVERLAP = 60


class DocumentStore:
    """
    Ingest PDF/DOCX files into a local ChromaDB vector store.
    Falls back to an in-memory lexical store when vector dependencies are unavailable.
    """

    def __init__(self) -> None:
        self._fallback_mode = not HAS_VECTOR_DEPS
        self._fallback_chunks: dict[str, dict[str, Any]] = {}

        if self._fallback_mode:
            logger.warning(
                "DocumentStore running in fallback mode; install chromadb, sentence-transformers, and langchain for semantic search."
            )
            return

        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self.embedder = SentenceTransformer(EMBED_MODEL)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        logger.info("DocumentStore ready - %d chunks indexed", self.collection.count())

    def add_document(self, file_path: Path, metadata: dict[str, Any] | None = None) -> int:
        """
        Parse and ingest a PDF or DOCX file.
        Returns the number of indexed chunks.
        """
        suffix = file_path.suffix.lower()
        if suffix not in (".pdf", ".docx"):
            raise ValueError(f"Unsupported file type: {suffix}. Only PDF and DOCX accepted.")

        if self._fallback_mode:
            return self._add_document_fallback(file_path=file_path, metadata=metadata)

        try:
            if suffix == ".pdf":
                loader = PyPDFLoader(str(file_path))
            else:
                loader = Docx2txtLoader(str(file_path))
            documents = loader.load()
        except Exception as exc:
            raise RuntimeError(f"Failed to parse document: {file_path.name}") from exc

        if not documents:
            raise RuntimeError(f"No readable content found in document: {file_path.name}")

        split_docs = self.splitter.split_documents(documents)
        if not split_docs:
            raise RuntimeError(f"Failed to split document into chunks: {file_path.name}")

        meta_base = {
            "source": self._sanitize_source_name(file_path.name),
            **(metadata or {}),
        }

        file_hash = self._hash_file(file_path)
        source_name = self._resolve_source_name(file_path=file_path, metadata=meta_base)
        source_hash = hashlib.sha256(source_name.encode("utf-8")).hexdigest()[:12]
        base_meta = self._base_metadata(
            file_path=file_path,
            file_hash=file_hash,
            source_name=source_name,
            metadata=meta_base,
        )

        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for idx, chunk in enumerate(split_docs):
            content = chunk.page_content.strip()
            if not content:
                continue

            chunk_meta: dict[str, Any] = dict(base_meta)
            chunk_meta.update(chunk.metadata or {})
            chunk_meta["chunk_index"] = idx

            ids.append(f"{file_hash}:{source_hash}:{idx}")
            texts.append(content)
            metadatas.append(chunk_meta)

        if not texts:
            raise RuntimeError(f"No non-empty chunks found in document: {file_path.name}")

        embeddings = self.embedder.encode(texts, normalize_embeddings=True).tolist()
        self.collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info("Indexed %d chunks from %s", len(texts), file_path.name)
        return len(texts)

    def query(self, text: str, n_results: int = 4, k: int | None = None) -> list[dict[str, Any]]:
        """
        Query similar chunks from the store for a natural-language question.

        Args:
            text: Query text.
            n_results: Number of chunks to return.
            k: Backward-compatible alias for n_results.
        """
        query_text = text.strip()
        if not query_text:
            return []

        requested_results = k if k is not None else n_results
        if self._fallback_mode:
            return self._query_fallback(text=query_text, n_results=requested_results)

        total_chunks = int(self.collection.count())
        if total_chunks == 0:
            return []

        query_embedding = self.embedder.encode([query_text], normalize_embeddings=True).tolist()
        try:
            results = self.collection.query(
                query_embeddings=query_embedding,
                n_results=max(1, min(requested_results, total_chunks)),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.warning("RAG query failed: %s", exc)
            return []

        docs = self._first_list(results.get("documents"))
        metas = self._first_list(results.get("metadatas"))
        dists = self._first_list(results.get("distances"))

        output: list[dict[str, Any]] = []
        for i, doc in enumerate(docs):
            output.append(
                {
                    "text": doc,
                    "metadata": metas[i] if i < len(metas) else {},
                    "distance": dists[i] if i < len(dists) else None,
                }
            )
        return output

    def count(self) -> int:
        """Return number of indexed chunks."""
        if self._fallback_mode:
            return len(self._fallback_chunks)
        return int(self.collection.count())

    def list_documents(self) -> list[dict[str, Any]]:
        """Return indexed source documents with chunk counts."""
        if self._fallback_mode:
            return self._list_documents_from_records(self._fallback_chunks.values())

        snapshot = self.collection.get(include=["metadatas"])
        ids = self._flatten(snapshot.get("ids"))
        metadatas = self._flatten(snapshot.get("metadatas"))
        if not ids:
            return []

        records: list[dict[str, Any]] = []
        for idx, _id in enumerate(ids):
            _ = _id
            meta = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
            records.append({"metadata": meta})
        return self._list_documents_from_records(records)

    def delete_document(self, source_name: str) -> int:
        """Delete all chunks for a source document. Returns number of deleted chunks."""
        raw_source = (source_name or "").strip()
        if not raw_source:
            return 0
        safe_name = self._sanitize_source_name(raw_source)

        if self._fallback_mode:
            ids_to_delete = [
                chunk_id
                for chunk_id, chunk in self._fallback_chunks.items()
                if self._extract_source(chunk.get("metadata")) == safe_name
            ]
            for chunk_id in ids_to_delete:
                self._fallback_chunks.pop(chunk_id, None)
            if ids_to_delete:
                logger.info("Deleted %d chunks for %s", len(ids_to_delete), safe_name)
            return len(ids_to_delete)

        snapshot = self.collection.get(
            where={"source": safe_name},
            include=["metadatas"],
        )
        ids = self._flatten(snapshot.get("ids"))
        if not ids:
            return 0

        self.collection.delete(ids=ids)
        logger.info("Deleted %d chunks for %s", len(ids), safe_name)
        return len(ids)

    def cleanup_old_documents(self, keep_latest: int = 20) -> int:
        """Delete oldest documents and keep only the latest N sources."""
        docs = self.list_documents()
        if len(docs) <= keep_latest:
            return 0

        deleted = 0
        for doc in docs[keep_latest:]:
            deleted += self.delete_document(doc["source"])
        return deleted

    def _add_document_fallback(self, file_path: Path, metadata: dict[str, Any] | None = None) -> int:
        """In-memory ingestion path used when vector dependencies are unavailable."""
        content = file_path.read_bytes()
        text = content.decode("utf-8", errors="replace")
        if not text.strip():
            text = f"Binary document: {file_path.name}"

        step = max(1, CHUNK_SIZE - CHUNK_OVERLAP)
        chunks = [text[i : i + CHUNK_SIZE].strip() for i in range(0, len(text), step)]
        chunks = [chunk for chunk in chunks if chunk]
        if not chunks:
            raise RuntimeError(f"No readable content found in document: {file_path.name}")

        meta_base = {
            "source": self._sanitize_source_name(file_path.name),
            **(metadata or {}),
        }

        file_hash = self._hash_file(file_path)
        source_name = self._resolve_source_name(file_path=file_path, metadata=meta_base)
        source_hash = hashlib.sha256(source_name.encode("utf-8")).hexdigest()[:12]
        base_meta = self._base_metadata(
            file_path=file_path,
            file_hash=file_hash,
            source_name=source_name,
            metadata=meta_base,
        )

        for idx, chunk in enumerate(chunks):
            chunk_id = f"{file_hash}:{source_hash}:{idx}"
            chunk_meta = dict(base_meta)
            chunk_meta["chunk_index"] = idx
            self._fallback_chunks[chunk_id] = {
                "text": chunk,
                "metadata": chunk_meta,
            }
        return len(chunks)

    def _query_fallback(self, text: str, n_results: int) -> list[dict[str, Any]]:
        if not self._fallback_chunks:
            return []

        query_terms = [term for term in text.lower().split() if term]
        scored: list[tuple[int, float, dict[str, Any]]] = []

        for chunk in self._fallback_chunks.values():
            chunk_text = str(chunk.get("text", ""))
            chunk_lower = chunk_text.lower()
            score = sum(chunk_lower.count(term) for term in query_terms)
            recency = self._to_float((chunk.get("metadata") or {}).get("ingested_at"))
            scored.append((score, recency, chunk))

        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)

        output: list[dict[str, Any]] = []
        for score, _, chunk in scored[: max(1, n_results)]:
            output.append(
                {
                    "text": chunk.get("text", ""),
                    "metadata": chunk.get("metadata", {}),
                    "distance": 1.0 / (1.0 + score),
                }
            )
        return output

    def _list_documents_from_records(self, records: Any) -> list[dict[str, Any]]:
        grouped: dict[str, int] = {}
        newest_ingest: dict[str, float] = {}

        for record in records:
            meta = record.get("metadata", {}) if isinstance(record, dict) else {}
            source = self._extract_source(meta)
            grouped[source] = grouped.get(source, 0) + 1

            ts = self._to_float(meta.get("ingested_at"))
            current = newest_ingest.get(source, float("-inf"))
            if ts > current:
                newest_ingest[source] = ts

        sorted_sources = sorted(
            grouped.keys(),
            key=lambda src: newest_ingest.get(src, float("-inf")),
            reverse=True,
        )
        return [{"source": source, "chunks": grouped[source]} for source in sorted_sources]

    @staticmethod
    def _resolve_source_name(file_path: Path, metadata: dict[str, Any] | None) -> str:
        source_name = file_path.name
        if metadata:
            requested_source = metadata.get("original_filename") or metadata.get("source")
            if isinstance(requested_source, str) and requested_source.strip():
                source_name = requested_source.strip()
        return DocumentStore._sanitize_source_name(source_name)

    @staticmethod
    def _sanitize_source_name(name: str) -> str:
        """Sanitize source document names used as identifiers/metadata."""
        clean = re.sub(r"[^a-zA-Z0-9._-]", "_", (name or "").strip())
        return clean[:128] or "upload"

    @staticmethod
    def _base_metadata(
        file_path: Path,
        file_hash: str,
        source_name: str,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        base_meta: dict[str, Any] = {
            "source": source_name,
            "original_filename": source_name,
            "source_path": str(file_path),
            "file_hash": file_hash,
            "ingested_at": time.time(),
        }
        if metadata:
            base_meta.update(metadata)
        base_meta["source"] = source_name
        return base_meta

    @staticmethod
    def _extract_source(meta: Any) -> str:
        if isinstance(meta, dict):
            return str(meta.get("source") or meta.get("original_filename") or "unknown")
        return "unknown"

    @staticmethod
    def _first_list(value: Any) -> list[Any]:
        if not isinstance(value, list):
            return []
        if value and isinstance(value[0], list):
            return value[0]
        return value

    @staticmethod
    def _flatten(value: Any) -> list[Any]:
        if not isinstance(value, list):
            return []
        if value and isinstance(value[0], list):
            flattened: list[Any] = []
            for item in value:
                if isinstance(item, list):
                    flattened.extend(item)
                else:
                    flattened.append(item)
            return flattened
        return value

    @staticmethod
    def _hash_file(file_path: Path) -> str:
        """Compute SHA256 hash of a file's bytes for stable document identity."""
        return hashlib.sha256(file_path.read_bytes()).hexdigest()

    @staticmethod
    def _to_float(value: Any) -> float:
        """Best-effort conversion helper for metadata timestamps."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("-inf")
