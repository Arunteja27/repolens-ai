from repolens.core.config import Settings
from repolens.models import RetrievedChunk
from repolens.services.answering import ExtractiveAnswerGenerator


def _settings(tmp_path):
    return Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / ".data",
        temp_repo_dir=tmp_path / ".data" / "repos",
        chroma_dir=tmp_path / ".data" / "chroma",
        database_path=tmp_path / ".data" / "repolens.db",
    )


def test_answer_generation_returns_citation_format(tmp_path) -> None:
    settings = _settings(tmp_path)
    generator = ExtractiveAnswerGenerator(settings)
    chunks = [
        RetrievedChunk(
            id="chunk-1",
            repo_id="repo-1",
            file_path="src/server.ts",
            language="typescript",
            start_line=1,
            end_line=4,
            chunk_text="Bootstraps the HTTP server and attaches request logging middleware.",
            chunk_hash="hash-1",
            score=0.91,
            source="hybrid",
        )
    ]

    answer = generator.generate("Where is the server bootstrapped?", chunks, request_id="req-1")

    assert answer.citations[0].file_path == "src/server.ts"
    assert answer.citations[0].start_line == 1
    assert "src/server.ts:1-4" in answer.answer


def test_answer_generation_returns_unknown_when_evidence_is_missing(tmp_path) -> None:
    generator = ExtractiveAnswerGenerator(_settings(tmp_path))
    chunks = [
        RetrievedChunk(
            id="chunk-1",
            repo_id="repo-1",
            file_path="src/ui/theme.ts",
            language="typescript",
            start_line=10,
            end_line=16,
            chunk_text="export function applyTheme(themeName: string) { return themeName; }",
            chunk_hash="hash-1",
            score=0.61,
            source="hybrid",
        )
    ]

    answer = generator.generate(
        "Where is the Postgres schema defined?",
        chunks,
        request_id="req-2",
    )

    assert answer.answer == "I don't know from the indexed repo."
    assert answer.citations == []


def test_answer_generation_answers_configuration_question(tmp_path) -> None:
    generator = ExtractiveAnswerGenerator(_settings(tmp_path))
    chunks = [
        RetrievedChunk(
            id="chunk-1",
            repo_id="repo-1",
            file_path="package.json",
            language="json",
            start_line=120,
            end_line=180,
            chunk_text="""
{
  "contributes": {
    "configuration": {
      "properties": {
        "codeSpa.themePreset": {
          "type": "string"
        }
      }
    }
  }
}
""".strip(),
            chunk_hash="hash-1",
            score=0.88,
            source="hybrid",
        )
    ]

    answer = generator.generate(
        "Where are Code Spa settings declared?",
        chunks,
        request_id="req-3",
    )

    assert "package.json:120-180" in answer.answer
    assert "contributes.configuration.properties" in answer.answer
