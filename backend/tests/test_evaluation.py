import json
from pathlib import Path

from repolens.models import AnswerResponse, Citation, RetrievedChunk
from repolens.services.evaluation import EvaluationService
from repolens.services.storage import MetadataStore


class FakeQueryService:
    def query(self, repo_id: str, question: str, retrieval_mode: str, top_k: int, request_id: str):
        del repo_id, retrieval_mode, top_k, request_id
        if "postgres schema" in question.lower():
            return AnswerResponse(
                answer="I don't know from the indexed repo.",
                citations=[],
                retrieved_chunks=[],
                model_used="extractive-grounded",
                prompt_version="test",
                latency_ms=13,
                estimated_cost_usd=0.0,
                token_usage=None,
                request_id="req-unknown",
            )
        if "latency" in question.lower():
            file_path = "src/middleware/requestLogger.ts"
            answer = (
                "Based on the indexed repo, "
                "src/middleware/requestLogger.ts:1-3 -> logs request latency."
            )
        else:
            file_path = "src/server.ts"
            answer = "Based on the indexed repo, src/server.ts:1-3 -> Bootstraps the HTTP server."
        return AnswerResponse(
            answer=answer,
            citations=[Citation(file_path=file_path, start_line=1, end_line=3)],
            retrieved_chunks=[
                RetrievedChunk(
                    id="chunk-1",
                    repo_id="repo-1",
                    file_path=file_path,
                    language="typescript",
                    start_line=1,
                    end_line=3,
                    chunk_text=answer,
                    chunk_hash="hash-1",
                    score=0.9,
                    source="hybrid",
                )
            ],
            model_used="extractive-fallback",
            prompt_version="test",
            latency_ms=42,
            estimated_cost_usd=0.0,
            token_usage=None,
            request_id="req-1",
        )


def test_eval_metrics_are_calculated(tmp_path: Path) -> None:
    store = MetadataStore(tmp_path / "eval.db")
    service = EvaluationService(store=store, query_service=FakeQueryService())
    eval_set = tmp_path / "eval.json"
    eval_set.write_text(
        json.dumps(
            [
                {
                    "question": "Where is the server bootstrapped?",
                    "expected_files": ["src/server.ts"],
                    "expected_answer_contains": ["Bootstraps the HTTP server"],
                    "must_not_contain": ["database migration"],
                },
                {
                    "question": "Where is latency logged?",
                    "expected_files": ["src/middleware/requestLogger.ts"],
                    "expected_answer_contains": ["logs request latency"],
                    "must_not_contain": ["database migration"],
                },
                {
                    "question": "Where is the Postgres schema defined?",
                    "expected_files": [],
                    "expected_answer_contains": ["I don't know from the indexed repo."],
                    "must_not_contain": ["database migration"],
                },
            ]
        ),
        encoding="utf-8",
    )

    summary = service.run(repo_id="repo-1", eval_set_path=str(eval_set))

    assert summary.retrieval_recall_at_5 == 1.0
    assert summary.mrr == 1.0
    assert summary.answer_contains_score == 1.0
    assert summary.hallucination_rate == 0.0
    assert summary.failure_rate == 0.0
