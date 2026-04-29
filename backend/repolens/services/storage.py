from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from repolens.models import ChunkRecord, EvalSummary, RepoRecord


class MetadataStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS repos (
                    repo_id TEXT PRIMARY KEY,
                    repo_url TEXT NOT NULL,
                    branch TEXT,
                    commit_sha TEXT,
                    indexed_at TEXT NOT NULL,
                    files_indexed INTEGER NOT NULL,
                    chunks_indexed INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    repo_id TEXT NOT NULL,
                    repo_url TEXT NOT NULL,
                    commit_sha TEXT,
                    file_path TEXT NOT NULL,
                    language TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    chunk_hash TEXT NOT NULL,
                    symbol_name TEXT,
                    symbol_type TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_repo_id ON chunks (repo_id);
                CREATE INDEX IF NOT EXISTS idx_chunks_repo_file ON chunks (repo_id, file_path);
                CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks (chunk_hash);

                CREATE TABLE IF NOT EXISTS embeddings (
                    provider TEXT NOT NULL,
                    chunk_hash TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (provider, chunk_hash)
                );

                CREATE TABLE IF NOT EXISTS evals (
                    eval_id TEXT PRIMARY KEY,
                    repo_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    summary_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_evals_repo_id ON evals (repo_id, created_at DESC);
                """
            )

    def upsert_repo(self, repo: RepoRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO repos (
                    repo_id, repo_url, branch, commit_sha, indexed_at, files_indexed, chunks_indexed, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repo_id) DO UPDATE SET
                    repo_url=excluded.repo_url,
                    branch=excluded.branch,
                    commit_sha=excluded.commit_sha,
                    indexed_at=excluded.indexed_at,
                    files_indexed=excluded.files_indexed,
                    chunks_indexed=excluded.chunks_indexed,
                    metadata_json=excluded.metadata_json
                """,
                (
                    repo.repo_id,
                    repo.repo_url,
                    repo.branch,
                    repo.commit_sha,
                    repo.indexed_at.isoformat(),
                    repo.files_indexed,
                    repo.chunks_indexed,
                    json.dumps(repo.metadata),
                ),
            )

    def get_repo(self, repo_id: str) -> RepoRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM repos WHERE repo_id = ?", (repo_id,)).fetchone()
        if row is None:
            return None
        return RepoRecord.model_validate(
            {
                "repo_id": row["repo_id"],
                "repo_url": row["repo_url"],
                "branch": row["branch"],
                "commit_sha": row["commit_sha"],
                "indexed_at": row["indexed_at"],
                "files_indexed": row["files_indexed"],
                "chunks_indexed": row["chunks_indexed"],
                "metadata": json.loads(row["metadata_json"]),
            }
        )

    def delete_repo(self, repo_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM repos WHERE repo_id = ?", (repo_id,))
            connection.execute("DELETE FROM chunks WHERE repo_id = ?", (repo_id,))

    def replace_chunks(self, repo_id: str, chunks: list[ChunkRecord]) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM chunks WHERE repo_id = ?", (repo_id,))
            connection.executemany(
                """
                INSERT INTO chunks (
                    id, repo_id, repo_url, commit_sha, file_path, language,
                    start_line, end_line, chunk_text, chunk_hash,
                    symbol_name, symbol_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.id,
                        chunk.repo_id,
                        chunk.repo_url,
                        chunk.commit_sha,
                        chunk.file_path,
                        chunk.language,
                        chunk.start_line,
                        chunk.end_line,
                        chunk.chunk_text,
                        chunk.chunk_hash,
                        chunk.symbol_name,
                        chunk.symbol_type,
                        chunk.created_at.isoformat(),
                    )
                    for chunk in chunks
                ],
            )

    def list_chunks(self, repo_id: str) -> list[ChunkRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM chunks WHERE repo_id = ? ORDER BY file_path, start_line", (repo_id,)
            ).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    def get_embeddings(self, provider: str, chunk_hashes: list[str]) -> dict[str, list[float]]:
        if not chunk_hashes:
            return {}
        placeholders = ", ".join(["?"] * len(chunk_hashes))
        query = (
            f"SELECT chunk_hash, vector_json FROM embeddings WHERE provider = ? AND chunk_hash IN ({placeholders})"
        )
        with self._connect() as connection:
            rows = connection.execute(query, (provider, *chunk_hashes)).fetchall()
        return {row["chunk_hash"]: json.loads(row["vector_json"]) for row in rows}

    def store_embeddings(self, provider: str, vectors: dict[str, list[float]], updated_at: str) -> None:
        if not vectors:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO embeddings (provider, chunk_hash, vector_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider, chunk_hash) DO UPDATE SET
                    vector_json=excluded.vector_json,
                    updated_at=excluded.updated_at
                """,
                [
                    (provider, chunk_hash, json.dumps(vector), updated_at)
                    for chunk_hash, vector in vectors.items()
                ],
            )

    def save_eval_summary(self, summary: EvalSummary) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO evals (eval_id, repo_id, created_at, summary_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(eval_id) DO UPDATE SET
                    repo_id=excluded.repo_id,
                    created_at=excluded.created_at,
                    summary_json=excluded.summary_json
                """,
                (
                    summary.eval_id,
                    summary.repo_id,
                    summary.created_at.isoformat(),
                    summary.model_dump_json(),
                ),
            )

    def get_latest_eval(self, repo_id: str) -> EvalSummary | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT summary_json FROM evals WHERE repo_id = ? ORDER BY created_at DESC LIMIT 1",
                (repo_id,),
            ).fetchone()
        if row is None:
            return None
        return EvalSummary.model_validate_json(row["summary_json"])

    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> ChunkRecord:
        return ChunkRecord.model_validate(
            {
                "id": row["id"],
                "repo_id": row["repo_id"],
                "repo_url": row["repo_url"],
                "commit_sha": row["commit_sha"],
                "file_path": row["file_path"],
                "language": row["language"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "chunk_text": row["chunk_text"],
                "chunk_hash": row["chunk_hash"],
                "symbol_name": row["symbol_name"],
                "symbol_type": row["symbol_type"],
                "created_at": row["created_at"],
            }
        )

