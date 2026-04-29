from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


RetrievalMode = Literal["vector", "bm25", "hybrid"]


class Citation(BaseModel):
    file_path: str
    start_line: int
    end_line: int


class TokenUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class ChunkRecord(BaseModel):
    id: str
    repo_id: str
    repo_url: str
    commit_sha: str | None = None
    file_path: str
    language: str
    start_line: int
    end_line: int
    chunk_text: str
    chunk_hash: str
    symbol_name: str | None = None
    symbol_type: str | None = None
    created_at: datetime
    embedding: list[float] | None = None


class RetrievedChunk(BaseModel):
    id: str
    repo_id: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    chunk_text: str
    chunk_hash: str
    symbol_name: str | None = None
    symbol_type: str | None = None
    score: float
    source: str


class RepoRecord(BaseModel):
    repo_id: str
    repo_url: str
    branch: str | None = None
    commit_sha: str | None = None
    indexed_at: datetime
    files_indexed: int
    chunks_indexed: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexRepoRequest(BaseModel):
    repo_url: str
    branch: str | None = None


class IndexRepoResponse(BaseModel):
    repo_id: str
    files_indexed: int
    chunks_indexed: int
    duration_ms: int


class QueryRequest(BaseModel):
    repo_id: str
    question: str
    retrieval_mode: RetrievalMode
    top_k: int | None = None


class AnswerResponse(BaseModel):
    answer: str
    citations: list[Citation]
    retrieved_chunks: list[RetrievedChunk]
    model_used: str
    prompt_version: str
    latency_ms: int
    estimated_cost_usd: float | None = None
    token_usage: TokenUsage | None = None
    request_id: str


class EvalSample(BaseModel):
    question: str
    expected_files: list[str] = Field(default_factory=list)
    expected_answer_contains: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)


class EvalItemResult(BaseModel):
    question: str
    expected_files: list[str]
    retrieved_files: list[str]
    retrieval_hit_at_3: bool
    retrieval_hit_at_5: bool
    reciprocal_rank: float
    answer_contains_score: float
    groundedness_score: float
    hallucination_flags: list[str]
    latency_ms: int
    estimated_cost_usd: float | None = None
    answer: str
    citations: list[Citation]


class EvalSummary(BaseModel):
    eval_id: str
    repo_id: str
    created_at: datetime
    total_queries: int
    retrieval_recall_at_3: float
    retrieval_recall_at_5: float
    mrr: float
    answer_contains_score: float
    groundedness_score: float
    hallucination_flags: int
    average_latency_ms: float
    p95_latency_ms: float
    average_cost_per_query: float
    failure_rate: float
    failed_items: list[EvalItemResult] = Field(default_factory=list)


class EvalRunRequest(BaseModel):
    repo_id: str
    eval_set_path: str | None = None
