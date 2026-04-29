from pathlib import Path

from repolens.core.config import Settings
from repolens.services.answering import ExtractiveAnswerGenerator
from repolens.services.chunking import SymbolAwareChunker
from repolens.services.embeddings import EmbeddingService, HashingEmbeddingProvider
from repolens.services.filtering import FileFilter
from repolens.services.ingestion import IngestionService, RepositoryCloner
from repolens.services.query import QueryService
from repolens.services.retrieval import RetrievalService
from repolens.services.storage import MetadataStore
from repolens.services.vector_store import InMemoryVectorStore


def test_end_to_end_fixture_index_and_query(tmp_path: Path) -> None:
    settings = Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / ".data",
        temp_repo_dir=tmp_path / ".data" / "repos",
        chroma_dir=tmp_path / ".data" / "chroma",
        database_path=tmp_path / ".data" / "repolens.db",
    )
    settings.ensure_directories()
    store = MetadataStore(settings.database_path)
    embeddings = EmbeddingService(store=store, provider=HashingEmbeddingProvider())
    vector_store = InMemoryVectorStore()
    ingestion = IngestionService(
        cloner=RepositoryCloner(settings.temp_repo_dir),
        file_filter=FileFilter(settings),
        chunker=SymbolAwareChunker(),
        embeddings=embeddings,
        store=store,
        vector_store=vector_store,
    )
    retrieval = RetrievalService(store=store, vector_store=vector_store, embeddings=embeddings)
    query = QueryService(
        store=store,
        retrieval=retrieval,
        answer_generator=ExtractiveAnswerGenerator(settings),
    )
    fixture_repo = Path(__file__).resolve().parents[2] / "fixtures" / "sample_repo"

    indexed = ingestion.index_repository(str(fixture_repo), request_id="test")
    response = query.query(
        repo_id=indexed.repo_id,
        question="Which file combines vector similarity and BM25?",
        retrieval_mode="hybrid",
        top_k=3,
        request_id="test-query",
    )

    assert response.citations
    assert any(citation.file_path == "src/retrieval/hybridRetriever.ts" for citation in response.citations)
