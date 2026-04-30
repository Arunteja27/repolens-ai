from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw is not None else default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    root_dir: Path
    data_dir: Path
    temp_repo_dir: Path
    chroma_dir: Path
    database_path: Path
    app_name: str = "RepoLens AI"
    api_prefix: str = "/api"
    embedding_provider: str = "hashing"
    vector_store_provider: str = "memory"
    answer_provider: str = "extractive"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    generation_model: str = "gemini-1.5-pro"
    vertex_project_id: str | None = None
    vertex_location: str = "us-central1"
    gemini_api_key: str | None = None
    chunking_strategy: str = "symbol"
    chunk_size_lines: int = 80
    chunk_overlap_lines: int = 20
    max_file_size_bytes: int = 200_000
    max_lockfile_size_bytes: int = 75_000
    default_top_k: int = 6
    enable_rerank: bool = True
    prompt_version: str = "v1.0-grounded-json"
    log_level: str = "INFO"
    retrieval_candidate_multiplier: int = 6
    metrics_namespace: str = "repolens"
    rate_limit_enabled: bool = False
    rate_limit_query_requests: int = 180
    rate_limit_query_window_seconds: int = 60
    rate_limit_index_requests: int = 20
    rate_limit_index_window_seconds: int = 600
    rate_limit_eval_requests: int = 20
    rate_limit_eval_window_seconds: int = 600
    cors_allowed_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    supported_extensions: set[str] = field(
        default_factory=lambda: {
            ".py",
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".java",
            ".rb",
            ".go",
            ".cpp",
            ".h",
            ".md",
            ".yml",
            ".yaml",
            ".json",
        }
    )

    @classmethod
    def from_env(cls) -> Settings:
        root_dir = Path(__file__).resolve().parents[3]
        data_dir = root_dir / ".data"
        temp_repo_dir = data_dir / "repos"
        chroma_dir = data_dir / "chroma"
        database_url = os.getenv("DATABASE_URL", "sqlite:///./.data/repolens.db")
        database_path = cls._database_path_from_url(database_url, root_dir)

        settings = cls(
            root_dir=root_dir,
            data_dir=data_dir,
            temp_repo_dir=temp_repo_dir,
            chroma_dir=chroma_dir,
            database_path=database_path,
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "hashing"),
            vector_store_provider=os.getenv("VECTOR_STORE_PROVIDER", "memory"),
            answer_provider=os.getenv("ANSWER_PROVIDER", "extractive"),
            embedding_model=os.getenv(
                "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
            ),
            generation_model=os.getenv("GENERATION_MODEL", "gemini-1.5-pro"),
            vertex_project_id=os.getenv("VERTEX_PROJECT_ID"),
            vertex_location=os.getenv("VERTEX_LOCATION", "us-central1"),
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
            chunking_strategy=os.getenv("CHUNKING_STRATEGY", "symbol"),
            chunk_size_lines=_env_int("CHUNK_SIZE_LINES", 80),
            chunk_overlap_lines=_env_int("CHUNK_OVERLAP_LINES", 20),
            max_file_size_bytes=_env_int("MAX_FILE_SIZE_BYTES", 200_000),
            max_lockfile_size_bytes=_env_int("MAX_LOCKFILE_SIZE_BYTES", 75_000),
            default_top_k=_env_int("TOP_K", 6),
            enable_rerank=_env_bool("ENABLE_RERANK", True),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            rate_limit_enabled=_env_bool(
                "RATE_LIMIT_ENABLED",
                os.getenv("K_SERVICE") is not None,
            ),
            rate_limit_query_requests=_env_int("RATE_LIMIT_QUERY_REQUESTS", 180),
            rate_limit_query_window_seconds=_env_int(
                "RATE_LIMIT_QUERY_WINDOW_SECONDS", 60
            ),
            rate_limit_index_requests=_env_int("RATE_LIMIT_INDEX_REQUESTS", 20),
            rate_limit_index_window_seconds=_env_int(
                "RATE_LIMIT_INDEX_WINDOW_SECONDS", 600
            ),
            rate_limit_eval_requests=_env_int("RATE_LIMIT_EVAL_REQUESTS", 20),
            rate_limit_eval_window_seconds=_env_int(
                "RATE_LIMIT_EVAL_WINDOW_SECONDS", 600
            ),
            cors_allowed_origins=_env_list(
                "CORS_ALLOWED_ORIGINS",
                ["http://localhost:5173", "http://127.0.0.1:5173"],
            ),
        )
        settings.ensure_directories()
        return settings

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.temp_repo_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _database_path_from_url(database_url: str, root_dir: Path) -> Path:
        if not database_url.startswith("sqlite:///"):
            raise ValueError("RepoLens currently supports sqlite DATABASE_URL values only.")
        raw_path = database_url.removeprefix("sqlite:///")
        path = Path(raw_path)
        if not path.is_absolute():
            path = root_dir / path
        return path
