from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from repolens.core.logging import get_logger, log_event
from repolens.models import ChunkRecord, IndexRepoResponse, RepoRecord
from repolens.services.chunking import SlidingWindowChunker, SymbolAwareChunker
from repolens.services.embeddings import EmbeddingService
from repolens.services.filtering import FileFilter
from repolens.services.storage import MetadataStore
from repolens.services.vector_store import VectorStore

logger = get_logger(__name__)


@dataclass(slots=True)
class PreparedRepository:
    repo_path: Path
    repo_url: str
    branch: str | None
    commit_sha: str | None


class RepositoryCloner:
    def __init__(self, temp_repo_dir: Path) -> None:
        self.temp_repo_dir = temp_repo_dir

    def prepare(self, repo_url: str, branch: str | None = None) -> PreparedRepository:
        if self._is_local_source(repo_url):
            return self._copy_local_repo(repo_url=repo_url, branch=branch)
        return self._clone_remote_repo(repo_url=repo_url, branch=branch)

    def _copy_local_repo(self, repo_url: str, branch: str | None) -> PreparedRepository:
        source = Path(repo_url.removeprefix("file://")).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"Repository source does not exist: {source}")
        target = Path(tempfile.mkdtemp(dir=self.temp_repo_dir))
        shutil.copytree(source, target, dirs_exist_ok=True)
        commit_sha = self._resolve_commit_sha(source)
        return PreparedRepository(
            repo_path=target,
            repo_url=repo_url,
            branch=branch,
            commit_sha=commit_sha,
        )

    def _clone_remote_repo(self, repo_url: str, branch: str | None) -> PreparedRepository:
        target = Path(tempfile.mkdtemp(dir=self.temp_repo_dir))
        command = ["git", "clone", "--depth", "1"]
        if branch:
            command.extend(["--branch", branch])
        command.extend([repo_url, str(target)])
        subprocess.run(command, check=True, capture_output=True, text=True)
        commit_sha = self._resolve_commit_sha(target)
        return PreparedRepository(
            repo_path=target,
            repo_url=repo_url,
            branch=branch,
            commit_sha=commit_sha,
        )

    @staticmethod
    def _resolve_commit_sha(repo_path: Path) -> str | None:
        git_dir = repo_path / ".git"
        if not git_dir.exists():
            return None
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    @staticmethod
    def _is_local_source(repo_url: str) -> bool:
        return (
            repo_url.startswith("file://")
            or repo_url.startswith("/")
            or repo_url.startswith(".")
        )


class IngestionService:
    def __init__(
        self,
        cloner: RepositoryCloner,
        file_filter: FileFilter,
        chunker: SlidingWindowChunker | SymbolAwareChunker,
        embeddings: EmbeddingService,
        store: MetadataStore,
        vector_store: VectorStore,
    ) -> None:
        self.cloner = cloner
        self.file_filter = file_filter
        self.chunker = chunker
        self.embeddings = embeddings
        self.store = store
        self.vector_store = vector_store

    def index_repository(
        self, repo_url: str, branch: str | None = None, request_id: str = "system"
    ) -> IndexRepoResponse:
        started_at = time.perf_counter()
        prepared = self.cloner.prepare(repo_url=repo_url, branch=branch)
        repo_id = build_repo_id(repo_url=repo_url, branch=branch)
        self.store.delete_repo(repo_id)
        self.vector_store.delete_repo(repo_id)

        try:
            source_files = self.file_filter.iter_source_files(prepared.repo_path)
            chunks = self._chunk_files(
                repo_id=repo_id,
                repo_url=repo_url,
                commit_sha=prepared.commit_sha,
                source_root=prepared.repo_path,
                source_files=source_files,
            )
            embedded = self.embeddings.embed_chunks(chunks)
            self.store.replace_chunks(repo_id, embedded.chunks)
            self.vector_store.upsert(embedded.chunks)

            duration_ms = int((time.perf_counter() - started_at) * 1000)
            repo_record = RepoRecord(
                repo_id=repo_id,
                repo_url=repo_url,
                branch=branch,
                commit_sha=prepared.commit_sha,
                indexed_at=datetime.now(UTC),
                files_indexed=len(source_files),
                chunks_indexed=len(embedded.chunks),
                metadata={
                    "embedding_cache_hits": embedded.cache_hits,
                    "embedding_duration_ms": embedded.duration_ms,
                    "request_id": request_id,
                },
            )
            self.store.upsert_repo(repo_record)
            log_event(
                logger,
                level=20,
                message="repository_indexed",
                request_id=request_id,
                repo_id=repo_id,
                repo_url=repo_url,
                files_indexed=len(source_files),
                chunks_indexed=len(embedded.chunks),
                duration_ms=duration_ms,
                embedding_cache_hits=embedded.cache_hits,
            )
            return IndexRepoResponse(
                repo_id=repo_id,
                files_indexed=len(source_files),
                chunks_indexed=len(embedded.chunks),
                duration_ms=duration_ms,
            )
        finally:
            shutil.rmtree(prepared.repo_path, ignore_errors=True)

    def _chunk_files(
        self,
        repo_id: str,
        repo_url: str,
        commit_sha: str | None,
        source_root: Path,
        source_files: list,
    ) -> list[ChunkRecord]:
        records: list[ChunkRecord] = []
        now = datetime.now(UTC)
        for source_file in source_files:
            text = source_file.absolute_path.read_text(encoding="utf-8", errors="ignore")
            chunk_drafts = self.chunker.chunk_text(
                file_path=source_file.file_path,
                text=text,
                language=source_file.language,
            )
            for chunk in chunk_drafts:
                chunk_hash = hashlib.sha256(chunk.chunk_text.encode("utf-8")).hexdigest()
                chunk_id = (
                    f"{repo_id}:{chunk.file_path}:{chunk.start_line}-{chunk.end_line}:"
                    f"{chunk_hash[:10]}"
                )
                records.append(
                    ChunkRecord(
                        id=chunk_id,
                        repo_id=repo_id,
                        repo_url=repo_url,
                        commit_sha=commit_sha,
                        file_path=chunk.file_path,
                        language=source_file.language,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        chunk_text=chunk.chunk_text,
                        chunk_hash=chunk_hash,
                        symbol_name=chunk.symbol_name,
                        symbol_type=chunk.symbol_type,
                        created_at=now,
                    )
                )
        deduped: dict[str, ChunkRecord] = {}
        for record in records:
            deduped[record.id] = record
        return list(deduped.values())


def build_repo_id(repo_url: str, branch: str | None) -> str:
    slug_source = repo_url.removeprefix("https://").removeprefix("http://").rstrip("/")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug_source).strip("-").lower()
    digest = hashlib.sha1(f"{repo_url}|{branch or 'default'}".encode()).hexdigest()[:8]
    return f"{slug[:32]}-{digest}"
