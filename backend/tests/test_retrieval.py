from datetime import UTC, datetime
from pathlib import Path

from repolens.models import ChunkRecord, RepoRecord
from repolens.services.embeddings import EmbeddingService, HashingEmbeddingProvider
from repolens.services.retrieval import RetrievalService
from repolens.services.storage import MetadataStore
from repolens.services.vector_store import InMemoryVectorStore


def test_retrieval_returns_expected_shape(tmp_path: Path) -> None:
    store = MetadataStore(tmp_path / "retrieval.db")
    repo = RepoRecord(
        repo_id="repo-1",
        repo_url="https://example.com/repo",
        indexed_at=datetime.now(UTC),
        files_indexed=2,
        chunks_indexed=2,
    )
    store.upsert_repo(repo)
    embedder = EmbeddingService(store=store, provider=HashingEmbeddingProvider())
    vector_store = InMemoryVectorStore()
    chunks = [
        _chunk("chunk-1", "src/server.ts", "Bootstraps the HTTP server."),
        _chunk("chunk-2", "src/retrieval.ts", "Combines vector similarity with BM25 scores."),
    ]
    embedded = embedder.embed_chunks(chunks)
    store.replace_chunks("repo-1", embedded.chunks)
    vector_store.upsert(embedded.chunks)
    retrieval = RetrievalService(
        store=store,
        vector_store=vector_store,
        embeddings=embedder,
    )

    result = retrieval.retrieve("repo-1", "Where is BM25 combined?", "hybrid", top_k=2)

    assert result.chunks
    first = result.chunks[0]
    assert first.file_path
    assert isinstance(first.start_line, int)
    assert isinstance(first.end_line, int)
    assert first.source in {"vector", "bm25", "hybrid"}


def _chunk(chunk_id: str, file_path: str, text: str) -> ChunkRecord:
    return ChunkRecord(
        id=chunk_id,
        repo_id="repo-1",
        repo_url="https://example.com/repo",
        commit_sha=None,
        file_path=file_path,
        language="typescript",
        start_line=1,
        end_line=3,
        chunk_text=text,
        chunk_hash=str(hash(text)),
        created_at=datetime.now(UTC),
    )

