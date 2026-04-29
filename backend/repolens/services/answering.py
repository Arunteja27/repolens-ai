from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

import httpx

from repolens.core.config import Settings
from repolens.models import Citation, RetrievedChunk, TokenUsage

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
                model_used="extractive-fallback",
                prompt_version=self.settings.prompt_version,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                estimated_cost_usd=0.0,
                token_usage=None,
            )

        selected = chunks[: min(3, len(chunks))]
        answer_lines = ["Based on the indexed repo, the most relevant context is:"]
        citations: list[Citation] = []
        for chunk in selected:
            preview = self._summarize_chunk(chunk.chunk_text)
            answer_lines.append(
                f"- {chunk.file_path}:{chunk.start_line}-{chunk.end_line} -> {preview}"
            )
            citations.append(
                Citation(
                    file_path=chunk.file_path,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                )
            )
        return GeneratedAnswer(
            answer="\n".join(answer_lines),
            citations=citations,
            model_used="extractive-fallback",
            prompt_version=self.settings.prompt_version,
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            estimated_cost_usd=0.0,
            token_usage=None,
        )

    @staticmethod
    def _summarize_chunk(chunk_text: str) -> str:
        lines = [line.strip() for line in chunk_text.splitlines() if line.strip()]
        preview = " ".join(lines) if len(lines) <= 8 else " ".join(lines[:4])
        if not preview:
            preview = "Relevant code chunk"
        return preview[:220]


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
