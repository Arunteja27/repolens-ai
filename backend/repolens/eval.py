from __future__ import annotations

import argparse
import json

from repolens.container import build_context


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RepoLens evaluation harness.")
    parser.add_argument("--repo-id", required=True, help="Indexed repository identifier.")
    parser.add_argument("--eval-set", required=True, help="Path to JSON or CSV evaluation set.")
    parser.add_argument(
        "--retrieval-mode",
        default="hybrid",
        choices=["vector", "bm25", "hybrid"],
        help="Retrieval mode to evaluate.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Top-k retrieved chunks to use.")
    args = parser.parse_args()

    context = build_context()
    summary = context.evaluation.run(
        repo_id=args.repo_id,
        eval_set_path=args.eval_set,
        retrieval_mode=args.retrieval_mode,
        top_k=args.top_k,
    )
    print(json.dumps(summary.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
