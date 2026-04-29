from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_./-]*")
CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")

DEFINITION_TERMS = {
    "define",
    "defined",
    "defines",
    "declare",
    "declared",
    "declares",
    "implement",
    "implemented",
    "implements",
}
CONFIGURATION_TERMS = {
    "settings",
    "configuration",
    "config",
    "properties",
    "commands",
    "command",
    "activation",
}
SCHEMA_TERMS = {
    "database",
    "migration",
    "migrations",
    "postgres",
    "postgresql",
    "prisma",
    "schema",
    "sql",
}
STOPWORDS = {
    "a",
    "about",
    "all",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "by",
    "code",
    "defined",
    "defines",
    "file",
    "files",
    "for",
    "from",
    "how",
    "implemented",
    "in",
    "is",
    "it",
    "main",
    "of",
    "on",
    "or",
    "repo",
    "repository",
    "spa",
    "the",
    "this",
    "to",
    "what",
    "where",
    "which",
}
LOW_SIGNAL_TOKENS = {"class", "function", "method", "integration", "implementation"}
README_FILENAMES = {"readme.md"}
DOC_FILENAMES = README_FILENAMES | {"changelog.md", "contributing.md"}


class ChunkLike(Protocol):
    file_path: str
    chunk_text: str
    symbol_name: str | None
    symbol_type: str | None
    start_line: int
    end_line: int


@dataclass(slots=True)
class QuestionAnalysis:
    raw: str
    normalized: str
    tokens: list[str]
    token_set: set[str]
    important_terms: list[str]
    identifier_terms: list[str]
    asks_for_definition: bool
    asks_for_configuration: bool
    asks_for_documentation: bool
    asks_for_readme: bool
    asks_for_license: bool
    asks_for_support: bool
    asks_for_features: bool
    asks_for_schema: bool
    asks_for_class: bool
    asks_for_function: bool
    asks_for_method: bool


@dataclass(slots=True)
class ChunkAssessment:
    score: float
    important_overlap: float
    identifier_overlap: float
    support_terms: list[str]
    symbol_exact_match: bool
    symbol_partial_match: bool
    declaration_match: bool
    path_match: bool
    preferred_file_match: bool


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in TOKEN_PATTERN.findall(text):
        lowered = raw_token.lower()
        tokens.append(lowered)
        for split in _split_identifier(raw_token):
            if split not in tokens:
                tokens.append(split)
    return tokens


def analyze_question(question: str) -> QuestionAnalysis:
    normalized = question.strip().lower()
    tokens = tokenize(question)
    token_set = set(tokens)
    identifier_terms = _identifier_terms(question, tokens, token_set)
    important_terms = [
        token
        for token in tokens
        if token not in STOPWORDS and token not in LOW_SIGNAL_TOKENS and len(token) > 2
    ]
    if not important_terms:
        important_terms = [token for token in tokens if token not in STOPWORDS]

    asks_for_readme = "readme" in token_set
    asks_for_license = "license" in token_set
    asks_for_support = ("report" in token_set and "issues" in token_set) or (
        "feature" in token_set and "requests" in token_set
    )
    asks_for_features = "feature" in token_set or "features" in token_set
    asks_for_documentation = asks_for_readme or asks_for_license or asks_for_support
    asks_for_definition = bool(token_set & DEFINITION_TERMS) or (
        ("where" in token_set or "which" in token_set)
        and ("file" in token_set or "files" in token_set)
    )
    asks_for_configuration = bool(token_set & CONFIGURATION_TERMS)
    asks_for_schema = bool(token_set & SCHEMA_TERMS)

    return QuestionAnalysis(
        raw=question,
        normalized=normalized,
        tokens=tokens,
        token_set=token_set,
        important_terms=important_terms,
        identifier_terms=identifier_terms,
        asks_for_definition=asks_for_definition,
        asks_for_configuration=asks_for_configuration,
        asks_for_documentation=asks_for_documentation,
        asks_for_readme=asks_for_readme,
        asks_for_license=asks_for_license,
        asks_for_support=asks_for_support,
        asks_for_features=asks_for_features,
        asks_for_schema=asks_for_schema,
        asks_for_class="class" in token_set,
        asks_for_function="function" in token_set,
        asks_for_method="method" in token_set,
    )


def assess_chunk(
    analysis: QuestionAnalysis,
    chunk: ChunkLike,
    *,
    base_score: float = 0.0,
) -> ChunkAssessment:
    path_lower = chunk.file_path.lower()
    file_name = PurePosixPath(path_lower).name
    symbol_name = chunk.symbol_name or ""
    symbol_lower = normalize_identifier(symbol_name)
    metadata_text = f"{chunk.file_path} {symbol_name} {chunk.symbol_type or ''} {chunk.chunk_text}"
    chunk_tokens = set(tokenize(metadata_text))

    important_overlap_terms = sorted(set(analysis.important_terms) & chunk_tokens)
    identifier_overlap_terms = sorted(set(analysis.identifier_terms) & chunk_tokens)
    important_overlap = len(important_overlap_terms) / max(1, len(set(analysis.important_terms)))
    identifier_overlap = len(identifier_overlap_terms) / max(1, len(set(analysis.identifier_terms)))

    path_terms = analysis.identifier_terms + analysis.important_terms
    path_match = any(term in path_lower for term in path_terms)
    preferred_file_match = _preferred_file_match(analysis, path_lower, file_name)
    symbol_exact_match = bool(
        symbol_lower
        and any(identifier == symbol_lower for identifier in analysis.identifier_terms)
    )
    symbol_partial_match = bool(
        symbol_lower
        and any(
            len(identifier) > 3 and identifier in symbol_lower
            for identifier in analysis.identifier_terms
        )
    )
    declaration_match = _matches_declaration(analysis, chunk)

    score = base_score * 0.2
    score += important_overlap * 0.35
    score += identifier_overlap * 0.15

    if symbol_exact_match:
        score += 0.45
    elif symbol_partial_match:
        score += 0.08
    if declaration_match:
        score += 0.35
    if path_match:
        score += 0.12
    if preferred_file_match:
        score += 0.35

    if is_documentation_file(path_lower) and not analysis.asks_for_documentation:
        score -= 0.08

    if analysis.asks_for_definition:
        if chunk.start_line <= 40:
            score += 0.05
        if file_name == "package.json" and not analysis.asks_for_configuration:
            score -= 0.15
        if is_documentation_file(path_lower) and not analysis.asks_for_documentation:
            score -= 0.18
        if _looks_like_import_only(chunk.chunk_text) and not declaration_match:
            score -= 0.12

    if analysis.asks_for_configuration:
        if file_name == "package.json":
            score += 0.45
        if '"configuration"' in chunk.chunk_text or "contributes" in chunk.chunk_text:
            score += 0.18
        if "codespa." in chunk.chunk_text.lower():
            score += 0.12

    if analysis.asks_for_readme and file_name in README_FILENAMES:
        score += 0.45
    if analysis.asks_for_license and (
        "license" in path_lower or file_name in README_FILENAMES or file_name == "package.json"
    ):
        score += 0.25
    if analysis.asks_for_support and file_name in README_FILENAMES:
        score += 0.3
    if analysis.asks_for_features and file_name in README_FILENAMES:
        score += 0.25

    if analysis.asks_for_schema:
        schema_hits = sum(
            1
            for term in SCHEMA_TERMS
            if term in path_lower or term in chunk.chunk_text.lower()
        )
        if schema_hits:
            score += min(0.6, schema_hits * 0.18)
        else:
            score -= 0.24

    return ChunkAssessment(
        score=round(score, 6),
        important_overlap=important_overlap,
        identifier_overlap=identifier_overlap,
        support_terms=important_overlap_terms or identifier_overlap_terms,
        symbol_exact_match=symbol_exact_match,
        symbol_partial_match=symbol_partial_match,
        declaration_match=declaration_match,
        path_match=path_match,
        preferred_file_match=preferred_file_match,
    )


def is_documentation_file(path: str) -> bool:
    file_name = PurePosixPath(path.lower()).name
    return file_name in DOC_FILENAMES or path.lower().startswith("docs/")


def normalize_identifier(value: str) -> str:
    return NON_ALNUM_PATTERN.sub("", value.lower())


def _split_identifier(value: str) -> list[str]:
    parts: list[str] = []
    for item in re.split(r"[./_-]+", value):
        if not item:
            continue
        camel_split = CAMEL_CASE_BOUNDARY.sub(" ", item).split()
        for token in camel_split:
            lowered = token.lower()
            if lowered and lowered not in parts:
                parts.append(lowered)
    return parts


def _identifier_terms(question: str, tokens: list[str], token_set: set[str]) -> list[str]:
    identifiers: list[str] = []
    for raw_token in TOKEN_PATTERN.findall(question):
        normalized = normalize_identifier(raw_token)
        if not normalized or normalized in STOPWORDS:
            continue
        if any(character.isupper() for character in raw_token) or "." in raw_token:
            identifiers.append(normalized)
    if not identifiers:
        for token in tokens:
            if token in SCHEMA_TERMS or (token not in STOPWORDS and len(token) > 4):
                identifiers.append(token)
    return list(dict.fromkeys(identifiers))


def _preferred_file_match(
    analysis: QuestionAnalysis, path_lower: str, file_name: str
) -> bool:
    if analysis.asks_for_readme:
        return file_name in README_FILENAMES
    if analysis.asks_for_license:
        return (
            "license" in path_lower
            or file_name in README_FILENAMES
            or file_name == "package.json"
        )
    if analysis.asks_for_configuration:
        return (
            file_name == "package.json"
            or path_lower.startswith("config/")
            or file_name.startswith("config.")
            or file_name in {"default.yml", "default.yaml"}
        )
    if analysis.asks_for_schema:
        return any(term in path_lower for term in SCHEMA_TERMS)
    if analysis.asks_for_support or analysis.asks_for_features:
        return file_name in README_FILENAMES
    return False


def _matches_declaration(analysis: QuestionAnalysis, chunk: ChunkLike) -> bool:
    text = chunk.chunk_text.lower()
    identifiers = analysis.identifier_terms
    if not identifiers:
        return False

    if analysis.asks_for_class:
        return any(
            re.search(rf"\b(?:export\s+)?class\s+{re.escape(identifier)}\b", text)
            for identifier in identifiers
        )
    if analysis.asks_for_function:
        return any(
            re.search(rf"\b(?:export\s+)?(?:async\s+)?function\s+{re.escape(identifier)}\b", text)
            for identifier in identifiers
        )
    if analysis.asks_for_method or analysis.asks_for_definition:
        return any(
            re.search(
                rf"\b(?:public|private|protected)?\s*(?:static\s+)?(?:async\s+)?{re.escape(identifier)}\s*\(",
                text,
            )
            or re.search(
                rf"\b(?:export\s+)?(?:const|let|var)\s+{re.escape(identifier)}\s*=",
                text,
            )
            or re.search(rf"\b(?:export\s+)?class\s+{re.escape(identifier)}\b", text)
            for identifier in identifiers
        )
    return False


def _looks_like_import_only(chunk_text: str) -> bool:
    lines = [line.strip() for line in chunk_text.splitlines() if line.strip()]
    if not lines:
        return False
    import_like = sum(1 for line in lines[:6] if line.startswith(("import ", "from ")))
    return import_like >= max(2, len(lines[:6]) - 1)
