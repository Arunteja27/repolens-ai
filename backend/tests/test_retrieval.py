from datetime import UTC, datetime
from pathlib import Path

from repolens.models import ChunkRecord, RepoRecord
from repolens.services.embeddings import EmbeddingService, HashingEmbeddingProvider
from repolens.services.retrieval import HeuristicReranker, RetrievalService
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


def test_definition_query_prefers_symbol_definition_chunk(tmp_path: Path) -> None:
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
        ChunkRecord(
            id="chunk-1",
            repo_id="repo-1",
            repo_url="https://example.com/repo",
            commit_sha=None,
            file_path="src/core/extension.ts",
            language="typescript",
            start_line=1,
            end_line=5,
            chunk_text="import { ControlPanelProvider } from '../providers/controlPanelProvider';",
            chunk_hash="import-hash",
            created_at=datetime.now(UTC),
        ),
        ChunkRecord(
            id="chunk-2",
            repo_id="repo-1",
            repo_url="https://example.com/repo",
            commit_sha=None,
            file_path="src/providers/controlPanelProvider.ts",
            language="typescript",
            start_line=1,
            end_line=20,
            chunk_text="export class ControlPanelProvider implements vscode.WebviewViewProvider {}",
            chunk_hash="class-hash",
            symbol_name="ControlPanelProvider",
            symbol_type="class",
            created_at=datetime.now(UTC),
        ),
    ]
    embedded = embedder.embed_chunks(chunks)
    store.replace_chunks("repo-1", embedded.chunks)
    vector_store.upsert(embedded.chunks)
    retrieval = RetrievalService(
        store=store,
        vector_store=vector_store,
        embeddings=embedder,
        reranker=HeuristicReranker(),
        candidate_multiplier=6,
    )

    result = retrieval.retrieve(
        "repo-1",
        "Which file defines the ControlPanelProvider class?",
        "hybrid",
        top_k=2,
    )

    assert result.chunks[0].file_path == "src/providers/controlPanelProvider.ts"


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
