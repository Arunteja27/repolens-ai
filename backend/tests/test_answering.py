from repolens.core.config import Settings
from repolens.models import RetrievedChunk
from repolens.services.answering import ExtractiveAnswerGenerator


def test_answer_generation_returns_citation_format(tmp_path) -> None:
    settings = Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / ".data",
        temp_repo_dir=tmp_path / ".data" / "repos",
        chroma_dir=tmp_path / ".data" / "chroma",
        database_path=tmp_path / ".data" / "repolens.db",
    )
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

