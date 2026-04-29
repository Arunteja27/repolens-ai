from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from repolens.container import AppContext
from repolens.models import (
    AnswerResponse,
    EvalRunRequest,
    EvalSummary,
    IndexRepoRequest,
    IndexRepoResponse,
    QueryRequest,
    RepoRecord,
)


router = APIRouter()


def _context(request: Request) -> AppContext:
    return request.app.state.context


@router.post("/repos/index", response_model=IndexRepoResponse)
def index_repo(payload: IndexRepoRequest, request: Request) -> IndexRepoResponse:
    try:
        return _context(request).ingestion.index_repository(
            repo_url=payload.repo_url,
            branch=payload.branch,
            request_id=request.state.request_id,
        )
    except Exception as exc:  # pragma: no cover - error path
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query", response_model=AnswerResponse)
def query_repo(payload: QueryRequest, request: Request) -> AnswerResponse:
    try:
        return _context(request).query.query(
            repo_id=payload.repo_id,
            question=payload.question,
            retrieval_mode=payload.retrieval_mode,
            top_k=payload.top_k or _context(request).settings.default_top_k,
            request_id=request.state.request_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - error path
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/repos/{repo_id}", response_model=RepoRecord)
def get_repo(repo_id: str, request: Request) -> RepoRecord:
    repo = _context(request).store.get_repo(repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found.")
    return repo


@router.get("/evals/{repo_id}", response_model=EvalSummary)
def latest_eval(repo_id: str, request: Request) -> EvalSummary:
    result = _context(request).evaluation.latest(repo_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No evals found for repo.")
    return result


@router.post("/evals/run", response_model=EvalSummary)
def run_eval(payload: EvalRunRequest, request: Request) -> EvalSummary:
    eval_path = payload.eval_set_path or str(
        _context(request).settings.root_dir / "evals" / "sample_eval.json"
    )
    resolved = Path(eval_path)
    if not resolved.is_absolute():
        resolved = _context(request).settings.root_dir / resolved
    try:
        return _context(request).evaluation.run(
            repo_id=payload.repo_id,
            eval_set_path=str(resolved),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - error path
        raise HTTPException(status_code=400, detail=str(exc)) from exc

