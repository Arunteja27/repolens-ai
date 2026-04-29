from __future__ import annotations

import logging
import time

from repolens.core.logging import get_logger, log_event
from repolens.models import AnswerResponse, RetrievalMode
from repolens.services.answering import GeneratedAnswer
from repolens.services.retrieval import RetrievalService
from repolens.services.storage import MetadataStore


logger = get_logger(__name__)


class QueryService:
    def __init__(
        self,
        store: MetadataStore,
        retrieval: RetrievalService,
        answer_generator,
    ) -> None:
        self.store = store
        self.retrieval = retrieval
        self.answer_generator = answer_generator

    def query(
        self,
        repo_id: str,
        question: str,
        retrieval_mode: RetrievalMode,
        top_k: int,
        request_id: str,
    ) -> AnswerResponse:
        repo = self.store.get_repo(repo_id)
        if repo is None:
            raise KeyError(f"Repo {repo_id} is not indexed.")
        started_at = time.perf_counter()
        retrieval_result = self.retrieval.retrieve(
            repo_id=repo_id,
            question=question,
            mode=retrieval_mode,
            top_k=top_k,
        )
        generated = self.answer_generator.generate(
            question=question,
            chunks=retrieval_result.chunks,
            request_id=request_id,
        )
        total_latency_ms = int((time.perf_counter() - started_at) * 1000)
        response = AnswerResponse(
            answer=generated.answer,
            citations=generated.citations,
            retrieved_chunks=retrieval_result.chunks,
            model_used=generated.model_used,
            prompt_version=generated.prompt_version,
            latency_ms=total_latency_ms,
            estimated_cost_usd=generated.estimated_cost_usd,
            token_usage=generated.token_usage,
            request_id=request_id,
        )
        log_event(
            logger,
            logging.INFO,
            "query_completed",
            request_id=request_id,
            repo_id=repo_id,
            retrieval_mode=retrieval_mode,
            top_k=top_k,
            total_latency_ms=total_latency_ms,
            vector_search_duration_ms=retrieval_result.vector_search_duration_ms,
            bm25_search_duration_ms=retrieval_result.bm25_search_duration_ms,
            rerank_duration_ms=retrieval_result.rerank_duration_ms,
            generation_duration_ms=generated.latency_ms,
            estimated_cost_usd=generated.estimated_cost_usd,
            token_usage=generated.token_usage.model_dump() if generated.token_usage else None,
        )
        return response

