from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass
from statistics import mean
from typing import Protocol

from repolens.models import ChunkRecord, RetrievalMode, RetrievedChunk
from repolens.services.embeddings import EmbeddingService
from repolens.services.relevance import analyze_question, assess_chunk, tokenize
from repolens.services.storage import MetadataStore
from repolens.services.vector_store import VectorStore

try:
    from rank_bm25 import BM25Okapi
except ImportError:  # pragma: no cover - optional dependency
    BM25Okapi = None

@dataclass(slots=True)
class RetrievalResult:
    chunks: list[RetrievedChunk]
    vector_search_duration_ms: int
    bm25_search_duration_ms: int
    rerank_duration_ms: int


class Reranker(Protocol):
    def rerank(
        self, question: str, chunks: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        ...


class HeuristicReranker:
    def rerank(
        self, question: str, chunks: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        analysis = analyze_question(question)
        reranked: list[RetrievedChunk] = []
        for chunk in chunks:
            assessment = assess_chunk(analysis, chunk, base_score=chunk.score)
            reranked.append(
                chunk.model_copy(
                    update={
                        "score": assessment.score,
                        "source": f"{chunk.source}+heuristic",
                    }
                )
            )
        ranked = sorted(reranked, key=lambda item: item.score, reverse=True)
        return RetrievalService._diversify_by_file(ranked, top_k=top_k)


class CrossEncoderReranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(
        self, question: str, chunks: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        model = self._load()
        scores = model.predict([(question, chunk.chunk_text) for chunk in chunks])
        scored_chunks = [
            chunk.model_copy(
                update={
                    "score": float(score),
                    "source": f"{chunk.source}+cross-encoder",
                }
            )
            for chunk, score in zip(chunks, scores, strict=True)
        ]
        return sorted(scored_chunks, key=lambda item: item.score, reverse=True)[:top_k]


class SimpleBM25:
    def __init__(self, tokenized_corpus: list[list[str]]) -> None:
        self.corpus = tokenized_corpus
        self.avg_doc_len = mean([len(doc) for doc in tokenized_corpus]) if tokenized_corpus else 0.0
        self.document_frequencies: Counter[str] = Counter()
        self.term_frequencies: list[Counter[str]] = [Counter(doc) for doc in tokenized_corpus]
        for document in tokenized_corpus:
            for token in set(document):
                self.document_frequencies[token] += 1
        self.doc_count = len(tokenized_corpus)

    def get_scores(self, query_tokens: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
        scores = [0.0] * self.doc_count
        for index, document in enumerate(self.corpus):
            doc_len = len(document) or 1
            term_counts = self.term_frequencies[index]
            score = 0.0
            for token in query_tokens:
                if token not in term_counts:
                    continue
                df = self.document_frequencies[token]
                idf = math.log(1 + ((self.doc_count - df + 0.5) / (df + 0.5)))
                tf = term_counts[token]
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * (doc_len / max(self.avg_doc_len, 1.0)))
                score += idf * (numerator / denominator)
            scores[index] = score
        return scores


class RetrievalService:
    MIN_CANDIDATE_POOL = 60

    def __init__(
        self,
        store: MetadataStore,
        vector_store: VectorStore,
        embeddings: EmbeddingService,
        reranker: Reranker | None = None,
        candidate_multiplier: int = 3,
    ) -> None:
        self.store = store
        self.vector_store = vector_store
        self.embeddings = embeddings
        self.reranker = reranker
        self.candidate_multiplier = candidate_multiplier

    def retrieve(
        self, repo_id: str, question: str, mode: RetrievalMode, top_k: int
    ) -> RetrievalResult:
        vector_duration = 0
        bm25_duration = 0
        rerank_duration = 0
        candidates = max(top_k, top_k * self.candidate_multiplier, self.MIN_CANDIDATE_POOL)

        vector_results: list[RetrievedChunk] = []
        if mode in {"vector", "hybrid"}:
            started_at = time.perf_counter()
            query_embedding = self.embeddings.embed_query(question)
            vector_results = self.vector_store.search(
                query_embedding=query_embedding,
                top_k=candidates,
                filters={"repo_id": repo_id},
            )
            vector_duration = int((time.perf_counter() - started_at) * 1000)

        bm25_results: list[RetrievedChunk] = []
        if mode in {"bm25", "hybrid"}:
            started_at = time.perf_counter()
            bm25_results = self._bm25_search(repo_id=repo_id, question=question, top_k=candidates)
            bm25_duration = int((time.perf_counter() - started_at) * 1000)

        if mode == "vector":
            merged = vector_results[:candidates]
        elif mode == "bm25":
            merged = bm25_results[:candidates]
        else:
            merged = self._hybrid_fuse(
                vector_results=vector_results,
                bm25_results=bm25_results,
            )[:candidates]

        if self.reranker is not None and merged:
            started_at = time.perf_counter()
            merged = self.reranker.rerank(question=question, chunks=merged, top_k=top_k)
            rerank_duration = int((time.perf_counter() - started_at) * 1000)
        else:
            merged = self._diversify_by_file(merged, top_k=top_k)

        return RetrievalResult(
            chunks=merged,
            vector_search_duration_ms=vector_duration,
            bm25_search_duration_ms=bm25_duration,
            rerank_duration_ms=rerank_duration,
        )

    def _bm25_search(self, repo_id: str, question: str, top_k: int) -> list[RetrievedChunk]:
        chunks = self.store.list_chunks(repo_id)
        if not chunks:
            return []
        tokenized_corpus = [self._bm25_document_tokens(chunk) for chunk in chunks]
        query_tokens = tokenize(question)
        if BM25Okapi is not None:
            scores = list(BM25Okapi(tokenized_corpus).get_scores(query_tokens))
        else:
            scores = SimpleBM25(tokenized_corpus).get_scores(query_tokens)
        ranked = sorted(
            zip(scores, chunks, strict=True),
            key=lambda item: item[0],
            reverse=True,
        )[:top_k]
        return [
            self._to_retrieved_chunk(chunk, score, source="bm25")
            for score, chunk in ranked
            if score > 0
        ]

    def _hybrid_fuse(
        self, vector_results: list[RetrievedChunk], bm25_results: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        combined: dict[str, RetrievedChunk] = {}
        scores: dict[str, float] = {}
        vector_weight = 0.45 if self.embeddings.provider.provider_name == "hashing" else 0.8
        for weight, source_results in (
            (vector_weight, vector_results),
            (1.0, bm25_results),
        ):
            for rank, chunk in enumerate(source_results, start=1):
                scores[chunk.id] = scores.get(chunk.id, 0.0) + (weight / (40 + rank))
                combined.setdefault(chunk.id, chunk)
        hydrated = [
            combined[chunk_id].model_copy(update={"score": score, "source": "hybrid"})
            for chunk_id, score in scores.items()
        ]
        return sorted(hydrated, key=lambda item: item.score, reverse=True)

    @staticmethod
    def _bm25_document_tokens(chunk: ChunkRecord) -> list[str]:
        path_tokens = tokenize(chunk.file_path) * 3
        symbol_tokens = tokenize(chunk.symbol_name or "") * 5
        type_tokens = tokenize(chunk.symbol_type or "") * 2
        text_tokens = tokenize(chunk.chunk_text)
        return path_tokens + symbol_tokens + type_tokens + text_tokens

    @staticmethod
    def _diversify_by_file(
        chunks: list[RetrievedChunk], *, top_k: int, max_chunks_per_file: int = 2
    ) -> list[RetrievedChunk]:
        kept: list[RetrievedChunk] = []
        per_file_counts: Counter[str] = Counter()
        for chunk in chunks:
            if per_file_counts[chunk.file_path] >= max_chunks_per_file:
                continue
            kept.append(chunk)
            per_file_counts[chunk.file_path] += 1
            if len(kept) >= top_k:
                break
        return kept

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
                "score": float(score),
                "source": source,
            }
        )
