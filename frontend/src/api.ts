import type {
  AnswerResponse,
  EvalSummary,
  IndexRepoResponse,
  RepoRecord,
  RetrievalMode,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(errorPayload.detail ?? `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function indexRepo(repoUrl: string, branch?: string): Promise<IndexRepoResponse> {
  return request<IndexRepoResponse>("/api/repos/index", {
    method: "POST",
    body: JSON.stringify({ repo_url: repoUrl, branch: branch || null }),
  });
}

export async function getRepo(repoId: string): Promise<RepoRecord> {
  return request<RepoRecord>(`/api/repos/${repoId}`);
}

export async function queryRepo(
  repoId: string,
  question: string,
  retrievalMode: RetrievalMode,
  topK: number
): Promise<AnswerResponse> {
  return request<AnswerResponse>("/api/query", {
    method: "POST",
    body: JSON.stringify({
      repo_id: repoId,
      question,
      retrieval_mode: retrievalMode,
      top_k: topK,
    }),
  });
}

export async function getLatestEval(repoId: string): Promise<EvalSummary> {
  return request<EvalSummary>(`/api/evals/${repoId}`);
}

export async function runEval(repoId: string, evalSetPath?: string): Promise<EvalSummary> {
  return request<EvalSummary>("/api/evals/run", {
    method: "POST",
    body: JSON.stringify({
      repo_id: repoId,
      eval_set_path: evalSetPath || null,
    }),
  });
}

