from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from uuid import uuid4

from repolens.models import EvalItemResult, EvalSample, EvalSummary
from repolens.services.query import QueryService
from repolens.services.storage import MetadataStore


class EvaluationService:
    def __init__(self, store: MetadataStore, query_service: QueryService) -> None:
        self.store = store
        self.query_service = query_service

    def run(
        self,
        repo_id: str,
        eval_set_path: str,
        retrieval_mode: str = "hybrid",
        top_k: int = 5,
    ) -> EvalSummary:
        samples = load_eval_samples(Path(eval_set_path))
        results: list[EvalItemResult] = []
        for index, sample in enumerate(samples, start=1):
            answer = self.query_service.query(
                repo_id=repo_id,
                question=sample.question,
                retrieval_mode=retrieval_mode,  # type: ignore[arg-type]
                top_k=top_k,
                request_id=f"eval-{repo_id}-{index}",
            )
            retrieved_files = [chunk.file_path for chunk in answer.retrieved_chunks]
            retrieval_hit_at_3 = any(file in retrieved_files[:3] for file in sample.expected_files)
            retrieval_hit_at_5 = any(file in retrieved_files[:5] for file in sample.expected_files)
            reciprocal_rank = self._reciprocal_rank(retrieved_files, sample.expected_files)
            answer_contains_score = self._answer_contains_score(
                answer.answer, sample.expected_answer_contains
            )
            groundedness_score = self._groundedness_score(
                cited_files=[citation.file_path for citation in answer.citations],
                retrieved_files=retrieved_files,
                answer_text=answer.answer,
            )
            hallucination_flags = self._hallucination_flags(
                answer_text=answer.answer,
                must_not_contain=sample.must_not_contain,
                citations=[citation.file_path for citation in answer.citations],
                retrieved_files=retrieved_files,
            )
            results.append(
                EvalItemResult(
                    question=sample.question,
                    expected_files=sample.expected_files,
                    retrieved_files=retrieved_files[:top_k],
                    retrieval_hit_at_3=retrieval_hit_at_3,
                    retrieval_hit_at_5=retrieval_hit_at_5,
                    reciprocal_rank=reciprocal_rank,
                    answer_contains_score=answer_contains_score,
                    groundedness_score=groundedness_score,
                    hallucination_flags=hallucination_flags,
                    latency_ms=answer.latency_ms,
                    estimated_cost_usd=answer.estimated_cost_usd,
                    answer=answer.answer,
                    citations=answer.citations,
                )
            )

        total_queries = len(results)
        failed_items = [
            result
            for result in results
            if (result.expected_files and not result.retrieval_hit_at_5)
            or result.hallucination_flags
            or (result.answer_contains_score < 1.0 and result.expected_files)
        ]
        summary = EvalSummary(
            eval_id=f"eval-{uuid4().hex[:10]}",
            repo_id=repo_id,
            created_at=datetime.now(UTC),
            total_queries=total_queries,
            retrieval_recall_at_3=mean(
                [1.0 if result.retrieval_hit_at_3 else 0.0 for result in results]
            )
            if results
            else 0.0,
            retrieval_recall_at_5=mean(
                [1.0 if result.retrieval_hit_at_5 else 0.0 for result in results]
            )
            if results
            else 0.0,
            mrr=mean([result.reciprocal_rank for result in results]) if results else 0.0,
            answer_contains_score=mean([result.answer_contains_score for result in results])
            if results
            else 0.0,
            groundedness_score=mean([result.groundedness_score for result in results])
            if results
            else 0.0,
            hallucination_flags=sum(len(result.hallucination_flags) for result in results),
            average_latency_ms=mean([result.latency_ms for result in results]) if results else 0.0,
            p95_latency_ms=self._percentile([result.latency_ms for result in results], 95),
            average_cost_per_query=mean(
                [(result.estimated_cost_usd or 0.0) for result in results]
            )
            if results
            else 0.0,
            failure_rate=(len(failed_items) / total_queries) if total_queries else 0.0,
            failed_items=failed_items,
        )
        self.store.save_eval_summary(summary)
        return summary

    def latest(self, repo_id: str) -> EvalSummary | None:
        return self.store.get_latest_eval(repo_id)

    @staticmethod
    def _reciprocal_rank(retrieved_files: list[str], expected_files: list[str]) -> float:
        for rank, file_path in enumerate(retrieved_files, start=1):
            if file_path in expected_files:
                return 1.0 / rank
        return 0.0

    @staticmethod
    def _answer_contains_score(answer: str, expected_terms: list[str]) -> float:
        if not expected_terms:
            return 1.0
        normalized_answer = answer.lower()
        matches = sum(1 for term in expected_terms if term.lower() in normalized_answer)
        return matches / len(expected_terms)

    @staticmethod
    def _groundedness_score(
        cited_files: list[str], retrieved_files: list[str], answer_text: str
    ) -> float:
        if answer_text.strip() == "I don't know from the indexed repo.":
            return 1.0
        if not cited_files:
            return 0.0
        grounded = sum(1 for file_path in cited_files if file_path in retrieved_files)
        return grounded / len(cited_files)

    @staticmethod
    def _hallucination_flags(
        answer_text: str,
        must_not_contain: list[str],
        citations: list[str],
        retrieved_files: list[str],
    ) -> list[str]:
        flags: list[str] = []
        normalized_answer = answer_text.lower()
        for forbidden in must_not_contain:
            if forbidden.lower() in normalized_answer:
                flags.append(f"must_not_contain:{forbidden}")
        if answer_text.strip() != "I don't know from the indexed repo." and not citations:
            flags.append("missing_citations")
        for cited_file in citations:
            if cited_file not in retrieved_files:
                flags.append(f"citation_not_retrieved:{cited_file}")
        return flags

    @staticmethod
    def _percentile(values: list[int], percentile: int) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = max(
            0,
            min(
                len(sorted_values) - 1,
                round((percentile / 100) * (len(sorted_values) - 1)),
            ),
        )
        return float(sorted_values[index])


def load_eval_samples(path: Path) -> list[EvalSample]:
    if path.suffix == ".json":
        return [EvalSample.model_validate(item) for item in json.loads(path.read_text())]
    if path.suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            samples: list[EvalSample] = []
            for row in reader:
                samples.append(
                    EvalSample(
                        question=row["question"],
                        expected_files=row.get("expected_files", "").split("|")
                        if row.get("expected_files")
                        else [],
                        expected_answer_contains=row.get("expected_answer_contains", "").split("|")
                        if row.get("expected_answer_contains")
                        else [],
                        must_not_contain=row.get("must_not_contain", "").split("|")
                        if row.get("must_not_contain")
                        else [],
                    )
                )
            return samples
    raise ValueError("Eval set must be a JSON or CSV file.")
