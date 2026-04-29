from datetime import UTC, datetime
from pathlib import Path

from repolens.models import ChunkRecord
from repolens.services.embeddings import EmbeddingService, HashingEmbeddingProvider
from repolens.services.storage import MetadataStore


class CountingProvider(HashingEmbeddingProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += len(texts)
        return super().embed_documents(texts)


def test_embedding_cache_reuses_existing_vectors(tmp_path: Path) -> None:
    store = MetadataStore(tmp_path / "cache.db")
    provider = CountingProvider()
    service = EmbeddingService(store=store, provider=provider)
    chunks = [
        _chunk("chunk-1", "duplicate text"),
        _chunk("chunk-2", "duplicate text"),
    ]

    first = service.embed_chunks(chunks)
    second = service.embed_chunks(chunks)

    assert first.embedded_count == 1
    assert second.embedded_count == 0
    assert second.cache_hits == 1
    assert provider.calls == 1


def _chunk(chunk_id: str, text: str) -> ChunkRecord:
    return ChunkRecord(
        id=chunk_id,
        repo_id="repo-1",
        repo_url="https://example.com/repo",
        commit_sha=None,
        file_path="src/demo.ts",
        language="typescript",
        start_line=1,
        end_line=3,
        chunk_text=text,
        chunk_hash=str(hash(text)),
        created_at=datetime.now(UTC),
    )

