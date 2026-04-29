from __future__ import annotations

from dataclasses import dataclass

from repolens.core.config import Settings
from repolens.core.metrics import MetricsRegistry
from repolens.services.answering import ExtractiveAnswerGenerator, GeminiAnswerGenerator
from repolens.services.chunking import SlidingWindowChunker, SymbolAwareChunker
from repolens.services.embeddings import (
    EmbeddingService,
    GoogleEmbeddingProvider,
    HashingEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from repolens.services.evaluation import EvaluationService
from repolens.services.filtering import FileFilter
from repolens.services.ingestion import IngestionService, RepositoryCloner
from repolens.services.query import QueryService
from repolens.services.retrieval import HeuristicReranker, RetrievalService
from repolens.services.storage import MetadataStore
from repolens.services.vector_store import ChromaVectorStore, InMemoryVectorStore


@dataclass(slots=True)
class AppContext:
    settings: Settings
    metrics: MetricsRegistry
    store: MetadataStore
    ingestion: IngestionService
    query: QueryService
    evaluation: EvaluationService


def build_context(settings: Settings | None = None) -> AppContext:
    settings = settings or Settings.from_env()
    metrics = MetricsRegistry(namespace=settings.metrics_namespace)
    store = MetadataStore(settings.database_path)
    embedder = EmbeddingService(store=store, provider=_build_embedding_provider(settings))
    vector_store = _build_vector_store(settings)
    reranker = HeuristicReranker() if settings.enable_rerank else None
    retrieval = RetrievalService(
        store=store,
        vector_store=vector_store,
        embeddings=embedder,
        reranker=reranker,
        candidate_multiplier=settings.retrieval_candidate_multiplier,
    )
    answer_generator = _build_answer_generator(settings)
    ingestion = IngestionService(
        cloner=RepositoryCloner(settings.temp_repo_dir),
        file_filter=FileFilter(settings),
        chunker=_build_chunker(settings),
        embeddings=embedder,
        store=store,
        vector_store=vector_store,
    )
    query = QueryService(store=store, retrieval=retrieval, answer_generator=answer_generator)
    evaluation = EvaluationService(store=store, query_service=query)
    return AppContext(
        settings=settings,
        metrics=metrics,
        store=store,
        ingestion=ingestion,
        query=query,
        evaluation=evaluation,
    )


def _build_embedding_provider(settings: Settings):
    provider = settings.embedding_provider.lower()
    if provider in {"hashing", "local-debug"}:
        return HashingEmbeddingProvider()
    if provider in {"sentence-transformers", "sentence_transformers", "st"}:
        return SentenceTransformerEmbeddingProvider(settings.embedding_model)
    if provider in {"gemini", "vertex", "google"}:
        return GoogleEmbeddingProvider(
            model_name=settings.embedding_model.removeprefix("models/"),
            gemini_api_key=settings.gemini_api_key,
            vertex_project_id=settings.vertex_project_id,
            vertex_location=settings.vertex_location,
        )
    raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")


def _build_vector_store(settings: Settings):
    provider = settings.vector_store_provider.lower()
    if provider in {"memory", "in-memory"}:
        return InMemoryVectorStore()
    if provider in {"chroma", "chromadb"}:
        return ChromaVectorStore(settings.chroma_dir)
    raise ValueError(f"Unsupported vector store provider: {settings.vector_store_provider}")


def _build_answer_generator(settings: Settings):
    provider = settings.answer_provider.lower()
    if provider == "extractive":
        return ExtractiveAnswerGenerator(settings)
    if provider in {"gemini", "google"}:
        return GeminiAnswerGenerator(settings)
    if provider == "auto":
        if settings.gemini_api_key or settings.vertex_project_id:
            return GeminiAnswerGenerator(settings)
        return ExtractiveAnswerGenerator(settings)
    raise ValueError(f"Unsupported answer provider: {settings.answer_provider}")


def _build_chunker(settings: Settings):
    if settings.chunking_strategy.lower() == "sliding":
        return SlidingWindowChunker(
            chunk_size_lines=settings.chunk_size_lines,
            overlap_lines=settings.chunk_overlap_lines,
        )
    return SymbolAwareChunker(
        chunk_size_lines=settings.chunk_size_lines,
        overlap_lines=settings.chunk_overlap_lines,
    )

