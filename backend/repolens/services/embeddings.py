from __future__ import annotations

import hashlib
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx

from repolens.models import ChunkRecord
from repolens.services.storage import MetadataStore


TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_./-]*")


class EmbeddingProvider(Protocol):
    provider_name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


@dataclass(slots=True)
class EmbeddingBatchResult:
    chunks: list[ChunkRecord]
    cache_hits: int
    embedded_count: int
    duration_ms: int


class HashingEmbeddingProvider:
    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions
        self.provider_name = "hashing"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.provider_name = f"sentence-transformers:{model_name}"
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [list(vector) for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class GoogleEmbeddingProvider:
    def __init__(
        self,
        model_name: str = "text-embedding-004",
        gemini_api_key: str | None = None,
        vertex_project_id: str | None = None,
        vertex_location: str = "us-central1",
    ) -> None:
        self.model_name = model_name
        self.gemini_api_key = gemini_api_key
        self.vertex_project_id = vertex_project_id
        self.vertex_location = vertex_location
        self.provider_name = "google-embeddings"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, task_type="RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], task_type="RETRIEVAL_QUERY")[0]

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        if self.vertex_project_id:
            return self._embed_vertex(texts=texts, task_type=task_type)
        if self.gemini_api_key:
            return self._embed_gemini(texts=texts, task_type=task_type)
        raise RuntimeError("GoogleEmbeddingProvider requires GEMINI_API_KEY or VERTEX_PROJECT_ID.")

    def _embed_gemini(self, texts: list[str], task_type: str) -> list[list[float]]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:batchEmbedContents"
        )
        payload = {
            "requests": [
                {
                    "model": f"models/{self.model_name}",
                    "taskType": task_type,
                    "content": {"parts": [{"text": text}]},
                }
                for text in texts
            ]
        }
        response = httpx.post(url, params={"key": self.gemini_api_key}, json=payload, timeout=60.0)
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings") or []
        return [self._extract_values(item) for item in embeddings]

    def _embed_vertex(self, texts: list[str], task_type: str) -> list[list[float]]:
        import google.auth
        from google.auth.transport.requests import Request

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        url = (
            f"https://{self.vertex_location}-aiplatform.googleapis.com/v1/projects/"
            f"{self.vertex_project_id}/locations/{self.vertex_location}/publishers/google/models/"
            f"{self.model_name}:predict"
        )
        payload = {
            "instances": [{"task_type": task_type, "content": text} for text in texts],
        }
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {credentials.token}"},
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        predictions = data.get("predictions") or []
        return [self._extract_values(item) for item in predictions]

    @staticmethod
    def _extract_values(item: dict) -> list[float]:
        if "values" in item:
            return list(item["values"])
        if "embedding" in item and "values" in item["embedding"]:
            return list(item["embedding"]["values"])
        if "embeddings" in item and "values" in item["embeddings"]:
            return list(item["embeddings"]["values"])
        raise ValueError("Embedding response did not include vector values.")


class EmbeddingService:
    def __init__(self, store: MetadataStore, provider: EmbeddingProvider) -> None:
        self.store = store
        self.provider = provider

    def embed_chunks(self, chunks: list[ChunkRecord]) -> EmbeddingBatchResult:
        started_at = time.perf_counter()
        unique_by_hash: dict[str, str] = {}
        for chunk in chunks:
            unique_by_hash.setdefault(chunk.chunk_hash, chunk.chunk_text)

        cached = self.store.get_embeddings(self.provider.provider_name, list(unique_by_hash))
        missing_hashes = [chunk_hash for chunk_hash in unique_by_hash if chunk_hash not in cached]
        missing_vectors: dict[str, list[float]] = {}
        if missing_hashes:
            texts = [unique_by_hash[chunk_hash] for chunk_hash in missing_hashes]
            vectors = self.provider.embed_documents(texts)
            missing_vectors = dict(zip(missing_hashes, vectors, strict=True))
            self.store.store_embeddings(
                provider=self.provider.provider_name,
                vectors=missing_vectors,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

        all_vectors = {**cached, **missing_vectors}
        hydrated_chunks = [
            chunk.model_copy(update={"embedding": all_vectors.get(chunk.chunk_hash)}) for chunk in chunks
        ]
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        return EmbeddingBatchResult(
            chunks=hydrated_chunks,
            cache_hits=len(cached),
            embedded_count=len(missing_vectors),
            duration_ms=duration_ms,
        )

    def embed_query(self, text: str) -> list[float]:
        return self.provider.embed_query(text)


def estimate_embedding_cost(text_count: int) -> float | None:
    rate = os.getenv("EMBEDDING_COST_PER_1K", "")
    if not rate:
        return None
    return float(rate) * (text_count / 1000)

