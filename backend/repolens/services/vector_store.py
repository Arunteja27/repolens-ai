from __future__ import annotations

import math
from pathlib import Path
from typing import Protocol

from repolens.models import ChunkRecord, RetrievedChunk


class VectorStore(Protocol):
    def upsert(self, chunks: list[ChunkRecord]) -> None:
        ...

    def search(
        self, query_embedding: list[float], top_k: int, filters: dict[str, str] | None = None
    ) -> list[RetrievedChunk]:
        ...

    def delete_repo(self, repo_id: str) -> None:
        ...


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(vector_a, vector_b, strict=False))
    denom_a = math.sqrt(sum(a * a for a in vector_a)) or 1.0
    denom_b = math.sqrt(sum(b * b for b in vector_b)) or 1.0
    return numerator / (denom_a * denom_b)


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._chunks: dict[str, ChunkRecord] = {}

    def upsert(self, chunks: list[ChunkRecord]) -> None:
        for chunk in chunks:
            if chunk.embedding is None:
                raise ValueError("Chunk embeddings are required before upsert.")
            self._chunks[chunk.id] = chunk

    def search(
        self, query_embedding: list[float], top_k: int, filters: dict[str, str] | None = None
    ) -> list[RetrievedChunk]:
        repo_id = filters.get("repo_id") if filters else None
        candidates = [
            chunk
            for chunk in self._chunks.values()
            if repo_id is None or chunk.repo_id == repo_id
        ]
        ranked = sorted(
            (
                (
                    cosine_similarity(query_embedding, chunk.embedding or []),
                    chunk,
                )
                for chunk in candidates
            ),
            key=lambda item: item[0],
            reverse=True,
        )[:top_k]
        return [self._to_retrieved_chunk(chunk, score, source="vector") for score, chunk in ranked]

    def delete_repo(self, repo_id: str) -> None:
        doomed_ids = [
            chunk_id
            for chunk_id, chunk in self._chunks.items()
            if chunk.repo_id == repo_id
        ]
        for chunk_id in doomed_ids:
            del self._chunks[chunk_id]

    @staticmethod
    def _to_retrieved_chunk(chunk: ChunkRecord, score: float, source: str) -> RetrievedChunk:
        return RetrievedChunk.model_validate(
            {
                "id": chunk.id,
                "repo_id": chunk.repo_id,
                "file_path": chunk.file_path,
                "language": chunk.language,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "chunk_text": chunk.chunk_text,
                "chunk_hash": chunk.chunk_hash,
                "symbol_name": chunk.symbol_name,
                "symbol_type": chunk.symbol_type,
                "score": score,
                "source": source,
            }
        )


class ChromaVectorStore:
    def __init__(self, chroma_dir: Path, collection_name: str = "repolens_chunks") -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._collection = self._client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, chunks: list[ChunkRecord]) -> None:
        if not chunks:
            return
        self._collection.upsert(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.chunk_text for chunk in chunks],
            embeddings=[chunk.embedding for chunk in chunks],
            metadatas=[self._metadata_for_chunk(chunk) for chunk in chunks],
        )

    def search(
        self, query_embedding: list[float], top_k: int, filters: dict[str, str] | None = None
    ) -> list[RetrievedChunk]:
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filters or None,
            include=["documents", "metadatas", "distances"],
        )
        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        ids = (results.get("ids") or [[]])[0]
        hydrated: list[RetrievedChunk] = []
        for chunk_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=False
        ):
            score = 1 - float(distance)
            hydrated.append(
                RetrievedChunk.model_validate(
                    {
                        "id": chunk_id,
                        "repo_id": metadata["repo_id"],
                        "file_path": metadata["file_path"],
                        "language": metadata["language"],
                        "start_line": int(metadata["start_line"]),
                        "end_line": int(metadata["end_line"]),
                        "chunk_text": document,
                        "chunk_hash": metadata["chunk_hash"],
                        "symbol_name": metadata.get("symbol_name") or None,
                        "symbol_type": metadata.get("symbol_type") or None,
                        "score": score,
                        "source": "vector",
                    }
                )
            )
        return hydrated

    def delete_repo(self, repo_id: str) -> None:
        self._collection.delete(where={"repo_id": repo_id})

    @staticmethod
    def _metadata_for_chunk(chunk: ChunkRecord) -> dict[str, str | int]:
        return {
            "repo_id": chunk.repo_id,
            "repo_url": chunk.repo_url,
            "commit_sha": chunk.commit_sha or "",
            "file_path": chunk.file_path,
            "language": chunk.language,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "chunk_hash": chunk.chunk_hash,
            "symbol_name": chunk.symbol_name or "",
            "symbol_type": chunk.symbol_type or "",
        }
