from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

import httpx

from repolens.core.config import Settings
from repolens.models import Citation, RetrievedChunk, TokenUsage
from repolens.services.relevance import (
    ChunkAssessment,
    QuestionAnalysis,
    analyze_question,
    assess_chunk,
    is_documentation_file,
    normalize_identifier,
)

JSON_BLOCK_PATTERN = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass(slots=True)
class GeneratedAnswer:
    answer: str
    citations: list[Citation]
    model_used: str
    prompt_version: str
    latency_ms: int
    estimated_cost_usd: float | None
    token_usage: TokenUsage | None


class ExtractiveAnswerGenerator:
    UNKNOWN_ANSWER = "I don't know from the indexed repo."

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(
        self, question: str, chunks: list[RetrievedChunk], request_id: str
    ) -> GeneratedAnswer:
        started_at = time.perf_counter()
        if not chunks:
            return self._unknown_response(started_at)

        analysis = analyze_question(question)
        assessed = sorted(
            [
                (chunk, assess_chunk(analysis, chunk, base_score=chunk.score))
                for chunk in chunks
            ],
            key=lambda item: item[1].score,
            reverse=True,
        )

        if not self._has_sufficient_evidence(analysis, assessed):
            return self._unknown_response(started_at)

        if analysis.asks_for_configuration:
            answer_text, citations = self._answer_configuration_question(assessed)
        elif analysis.asks_for_documentation:
            answer_text, citations = self._answer_documentation_question(analysis, assessed)
        elif analysis.asks_for_definition:
            answer_text, citations = self._answer_definition_question(analysis, assessed)
        else:
            answer_text, citations = self._answer_generic_question(assessed)

        return GeneratedAnswer(
            answer=answer_text,
            citations=citations,
            model_used="extractive-grounded",
            prompt_version=self.settings.prompt_version,
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            estimated_cost_usd=0.0,
            token_usage=None,
        )

    def _unknown_response(self, started_at: float) -> GeneratedAnswer:
        return GeneratedAnswer(
            answer=self.UNKNOWN_ANSWER,
            citations=[],
            model_used="extractive-grounded",
            prompt_version=self.settings.prompt_version,
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            estimated_cost_usd=0.0,
            token_usage=None,
        )

    def _has_sufficient_evidence(
        self,
        analysis: QuestionAnalysis,
        assessed: list[tuple[RetrievedChunk, ChunkAssessment]],
    ) -> bool:
        if not assessed:
            return False
        best_chunk, best_assessment = assessed[0]
        if analysis.asks_for_schema:
            return best_assessment.preferred_file_match or bool(best_assessment.support_terms)
        if analysis.asks_for_configuration:
            return best_assessment.preferred_file_match or (
                best_assessment.score >= 0.45
                and (
                    "configuration" in best_chunk.chunk_text.lower()
                    or "config" in best_chunk.file_path.lower()
                )
            )
        if analysis.asks_for_definition:
            return (
                best_assessment.symbol_exact_match
                or best_assessment.symbol_partial_match
                or best_assessment.declaration_match
                or (best_assessment.path_match and best_assessment.score >= 0.65)
                or (best_assessment.score >= 0.4 and len(best_assessment.support_terms) >= 2)
            )
        if analysis.asks_for_documentation:
            return best_assessment.preferred_file_match or bool(best_assessment.support_terms)
        return best_assessment.score >= 0.3 and bool(best_assessment.support_terms)

    def _answer_definition_question(
        self,
        analysis: QuestionAnalysis,
        assessed: list[tuple[RetrievedChunk, ChunkAssessment]],
    ) -> tuple[str, list[Citation]]:
        best_chunk, _ = assessed[0]
        related_chunks = self._distinct_chunks(analysis, assessed, limit=2)
        subject = self._question_subject(analysis, best_chunk)
        descriptor = self._descriptor_for_question(analysis, subject)
        citations = [self._citation(chunk) for chunk in related_chunks]
        detail = self._supporting_detail(analysis, best_chunk)

        if "integration" in analysis.token_set and len(related_chunks) > 1:
            answer = (
                f"The strongest implementation for {descriptor} appears in "
                f"`{self._citation_label(related_chunks[0])}` and "
                f"`{self._citation_label(related_chunks[1])}`. {detail}"
            )
            return answer, citations

        answer = f"The {descriptor} is defined in `{self._citation_label(best_chunk)}`. {detail}"
        return answer, citations[:1]

    def _answer_configuration_question(
        self, assessed: list[tuple[RetrievedChunk, ChunkAssessment]]
    ) -> tuple[str, list[Citation]]:
        best_chunk, _ = assessed[0]
        property_name = self._first_config_property(best_chunk.chunk_text)
        detail = self._summarize_chunk(best_chunk.chunk_text)
        if property_name or "contributes" in best_chunk.chunk_text:
            property_hint = f", including `{property_name}`" if property_name else ""
            answer = (
                "Settings are declared in "
                f"`{self._citation_label(best_chunk)}` under `contributes.configuration.properties`"
                f"{property_hint}. {detail}"
            )
        else:
            answer = (
                f"The relevant configuration is in `{self._citation_label(best_chunk)}`. {detail}"
            )
        return answer, [self._citation(best_chunk)]

    def _answer_documentation_question(
        self,
        analysis: QuestionAnalysis,
        assessed: list[tuple[RetrievedChunk, ChunkAssessment]],
    ) -> tuple[str, list[Citation]]:
        best_chunk, _ = assessed[0]
        lines = [line.strip() for line in best_chunk.chunk_text.splitlines() if line.strip()]

        if analysis.asks_for_license:
            license_line = None
            for index, line in enumerate(lines):
                lowered = line.lower()
                if "rights reserved" in lowered:
                    license_line = self._strip_markdown(line)
                    break
                if "license" in lowered and index + 1 < len(lines):
                    license_line = self._strip_markdown(lines[index + 1])
                    break
            if license_line:
                answer = (
                    f"The repo lists `{license_line}` in "
                    f"`{self._citation_label(best_chunk)}`."
                )
                return answer, [self._citation(best_chunk)]

        if analysis.asks_for_support:
            matching_lines = [
                self._strip_markdown(line)
                for line in lines
                if "report issues" in line.lower()
                or "feature requests" in line.lower()
                or "contact support" in line.lower()
            ]
            if matching_lines:
                destinations = " and ".join(f"`{line}`" for line in matching_lines[:2])
                answer = f"Users can use {destinations}."
                return answer, [self._citation(best_chunk)]

        if analysis.asks_for_features:
            headings = [self._strip_markdown(line) for line in lines if line.startswith("### ")]
            if len(headings) >= 2:
                answer = f"The README highlights `{headings[0]}` and `{headings[1]}`."
                return answer, [self._citation(best_chunk)]

        relevant_lines = self._relevant_lines(analysis, best_chunk.chunk_text)
        if relevant_lines:
            answer = (
                f"Based on `{self._citation_label(best_chunk)}`, "
                + " ".join(relevant_lines[:3])
            )
            return answer, [self._citation(best_chunk)]
        return self._answer_generic_question(assessed)

    def _answer_generic_question(
        self, assessed: list[tuple[RetrievedChunk, ChunkAssessment]]
    ) -> tuple[str, list[Citation]]:
        best_chunk, _ = assessed[0]
        preview = self._summarize_chunk(best_chunk.chunk_text)
        answer = (
            f"The strongest grounded match is in `{self._citation_label(best_chunk)}`: {preview}"
        )
        return answer, [self._citation(best_chunk)]

    @staticmethod
    def _citation(chunk: RetrievedChunk) -> Citation:
        return Citation(
            file_path=chunk.file_path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
        )

    @staticmethod
    def _citation_label(chunk: RetrievedChunk) -> str:
        return f"{chunk.file_path}:{chunk.start_line}-{chunk.end_line}"

    @staticmethod
    def _distinct_chunks(
        analysis: QuestionAnalysis,
        assessed: list[tuple[RetrievedChunk, ChunkAssessment]],
        limit: int,
    ) -> list[RetrievedChunk]:
        selected: list[RetrievedChunk] = []
        seen_files: set[str] = set()
        for chunk, assessment in assessed:
            if chunk.file_path in seen_files:
                continue
            if not analysis.asks_for_documentation and is_documentation_file(chunk.file_path):
                continue
            if not (
                assessment.symbol_exact_match
                or assessment.symbol_partial_match
                or assessment.declaration_match
                or assessment.preferred_file_match
                or assessment.path_match
                or (assessment.score >= 0.45 and bool(assessment.support_terms))
            ):
                continue
            selected.append(chunk)
            seen_files.add(chunk.file_path)
            if len(selected) >= limit:
                break
        return selected or [assessed[0][0]]

    @staticmethod
    def _question_subject(analysis: QuestionAnalysis, chunk: RetrievedChunk) -> str:
        if chunk.symbol_name:
            return chunk.symbol_name
        return chunk.file_path

    @staticmethod
    def _descriptor_for_question(analysis: QuestionAnalysis, subject: str) -> str:
        if analysis.asks_for_class:
            return f"`{subject}` class"
        if analysis.asks_for_method:
            return f"`{subject}` method"
        if analysis.asks_for_function:
            return f"`{subject}` function"
        if analysis.asks_for_configuration:
            return "configuration"
        return "relevant implementation"

    @staticmethod
    def _summarize_chunk(chunk_text: str) -> str:
        lines = [line.strip() for line in chunk_text.splitlines() if line.strip()]
        preview = " ".join(lines) if len(lines) <= 8 else " ".join(lines[:4])
        if not preview:
            preview = "Relevant code chunk"
        return preview[:220]

    def _supporting_detail(self, analysis: QuestionAnalysis, chunk: RetrievedChunk) -> str:
        relevant_lines = self._relevant_lines(analysis, chunk.chunk_text)
        if relevant_lines:
            return "The retrieved chunk mentions " + " ".join(relevant_lines[:2])
        return self._summarize_chunk(chunk.chunk_text)

    @staticmethod
    def _first_config_property(chunk_text: str) -> str | None:
        match = re.search(r'"(codeSpa\.[^"]+)"\s*:', chunk_text)
        return match.group(1) if match else None

    @staticmethod
    def _strip_markdown(line: str) -> str:
        return re.sub(r"^[#*\-\s`>]+", "", line).strip()

    def _relevant_lines(self, analysis: QuestionAnalysis, chunk_text: str) -> list[str]:
        lines = [line.strip() for line in chunk_text.splitlines() if line.strip()]
        if not lines:
            return []
        scored_lines: list[tuple[int, str]] = []
        for line in lines:
            line_tokens = {
                normalize_identifier(token)
                for token in re.findall(r"[A-Za-z0-9_.-]+", line)
            }
            overlap = len(line_tokens & set(analysis.identifier_terms))
            overlap += len(set(line.lower().split()) & set(analysis.important_terms))
            if overlap <= 0 and not line.startswith(("### ", "- ", "* ")):
                continue
            if line.startswith(("### ", "- ", "* ")):
                overlap += 1
            scored_lines.append((overlap, self._strip_markdown(line)))
        scored_lines.sort(key=lambda item: item[0], reverse=True)
        return [line for _, line in scored_lines[:4]]


class GeminiAnswerGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(
        self, question: str, chunks: list[RetrievedChunk], request_id: str
    ) -> GeneratedAnswer:
        started_at = time.perf_counter()
        if not chunks:
            return GeneratedAnswer(
                answer="I don't know from the indexed repo.",
                citations=[],
                model_used=self.settings.generation_model,
                prompt_version=self.settings.prompt_version,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                estimated_cost_usd=0.0,
                token_usage=None,
            )

        prompt, citation_lookup = self._build_prompt(question=question, chunks=chunks)
        raw_response = self._call_model(prompt)
        parsed = self._parse_json_response(raw_response)
        citation_ids = parsed.get("citations", [])
        citations = [
            citation_lookup[citation_id]
            for citation_id in citation_ids
            if citation_id in citation_lookup
        ]
        usage = self._extract_usage(parsed.get("_usage"))
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        return GeneratedAnswer(
            answer=parsed.get("answer", "I don't know from the indexed repo."),
            citations=citations,
            model_used=self.settings.generation_model,
            prompt_version=self.settings.prompt_version,
            latency_ms=latency_ms,
            estimated_cost_usd=self._estimate_cost(usage),
            token_usage=usage,
        )

    def _call_model(self, prompt: str) -> dict:
        if self.settings.vertex_project_id:
            return self._call_vertex(prompt)
        if self.settings.gemini_api_key:
            return self._call_gemini_api(prompt)
        raise RuntimeError("GeminiAnswerGenerator requires GEMINI_API_KEY or VERTEX_PROJECT_ID.")

    def _call_gemini_api(self, prompt: str) -> dict:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.generation_model}:generateContent"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        response = httpx.post(
            url,
            params={"key": self.settings.gemini_api_key},
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()

    def _call_vertex(self, prompt: str) -> dict:
        import google.auth
        from google.auth.transport.requests import Request

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        url = (
            f"https://{self.settings.vertex_location}-aiplatform.googleapis.com/v1/projects/"
            f"{self.settings.vertex_project_id}/locations/{self.settings.vertex_location}/publishers/google/models/"
            f"{self.settings.generation_model}:generateContent"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {credentials.token}"},
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()

    def _build_prompt(
        self, question: str, chunks: list[RetrievedChunk]
    ) -> tuple[str, dict[str, Citation]]:
        citation_lookup: dict[str, Citation] = {}
        context_blocks: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            citation_id = f"C{index}"
            citation_lookup[citation_id] = Citation(
                file_path=chunk.file_path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
            )
            context_blocks.append(
                "\n".join(
                    [
                        f"[{citation_id}] {chunk.file_path}:{chunk.start_line}-{chunk.end_line}",
                        chunk.chunk_text,
                    ]
                )
            )
        instructions = (
            "You are RepoLens AI. Answer only from the retrieved repository context.\n"
            'If the context is insufficient, answer exactly: "I don\'t know from the '
            'indexed repo."\n'
            "Return strict JSON with this shape:\n"
            '{"answer": "...", "citations": ["C1", "C2"]}\n'
            "Do not invent files, line numbers, or APIs.\n"
        )
        prompt = (
            f"{instructions}\nQuestion:\n{question}\n\nRetrieved context:\n"
            + "\n\n---\n\n".join(context_blocks)
        )
        return prompt, citation_lookup

    def _parse_json_response(self, payload: dict) -> dict:
        text = self._extract_text(payload)
        if not text:
            return {
                "answer": "I don't know from the indexed repo.",
                "citations": [],
                "_usage": payload,
            }
        try:
            return {**json.loads(text), "_usage": payload}
        except json.JSONDecodeError:
            fenced = JSON_BLOCK_PATTERN.search(text)
            if fenced:
                return {**json.loads(fenced.group(1)), "_usage": payload}
        return {
            "answer": "I don't know from the indexed repo.",
            "citations": [],
            "_usage": payload,
        }

    @staticmethod
    def _extract_text(payload: dict) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            return ""
        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts") or []
        texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
        return "\n".join(texts).strip()

    @staticmethod
    def _extract_usage(payload: dict | None) -> TokenUsage | None:
        if not payload:
            return None
        usage = payload.get("usageMetadata") or payload.get("usage_metadata")
        if not usage:
            return None
        input_tokens = usage.get("promptTokenCount") or usage.get("prompt_token_count")
        output_tokens = usage.get("candidatesTokenCount") or usage.get("candidates_token_count")
        total_tokens = usage.get("totalTokenCount") or usage.get("total_token_count")
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _estimate_cost(token_usage: TokenUsage | None) -> float | None:
        if token_usage is None:
            return None
        input_rate = os.getenv("GENERATION_INPUT_COST_PER_MILLION")
        output_rate = os.getenv("GENERATION_OUTPUT_COST_PER_MILLION")
        if not input_rate or not output_rate:
            return None
        return round(
            ((token_usage.input_tokens or 0) / 1_000_000) * float(input_rate)
            + ((token_usage.output_tokens or 0) / 1_000_000) * float(output_rate),
            6,
        )
