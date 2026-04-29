from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from repolens.container import build_context  # noqa: E402


def main() -> None:
    os.environ.setdefault("EMBEDDING_PROVIDER", "hashing")
    os.environ.setdefault("VECTOR_STORE_PROVIDER", "memory")
    os.environ.setdefault("ANSWER_PROVIDER", "extractive")
    os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/repolens.db")

    context = build_context()
    fixture_repo = ROOT / "fixtures" / "sample_repo"
    eval_set = ROOT / "evals" / "sample_eval.json"

    index_result = context.ingestion.index_repository(str(fixture_repo), request_id="sample-eval")
    summary = context.evaluation.run(repo_id=index_result.repo_id, eval_set_path=str(eval_set))

    payload = {
        "repo_id": index_result.repo_id,
        "files_indexed": index_result.files_indexed,
        "chunks_indexed": index_result.chunks_indexed,
        "eval_summary": summary.model_dump(mode="json"),
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

