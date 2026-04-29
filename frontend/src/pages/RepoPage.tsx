import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getRepo, queryRepo } from "../api";
import { MetricCard } from "../components/MetricCard";
import { QueryResults } from "../components/QueryResults";
import type { AnswerResponse, RepoRecord, RetrievalMode } from "../types";

export function RepoPage() {
  const { repoId = "" } = useParams();
  const [repo, setRepo] = useState<RepoRecord | null>(null);
  const [question, setQuestion] = useState("Where is the main entrypoint and how does request logging work?");
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>("hybrid");
  const [topK, setTopK] = useState(6);
  const [result, setResult] = useState<AnswerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getRepo(repoId)
      .then(setRepo)
      .catch((repoError: Error) => setError(repoError.message));
  }, [repoId]);

  async function handleQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await queryRepo(repoId, question, retrievalMode, topK);
      setResult(response);
    } catch (queryError) {
      setError(queryError instanceof Error ? queryError.message : "Query failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="stack">
      <div className="page-header">
        <div>
          <span className="eyebrow">Indexed repository</span>
          <h1>{repo?.repo_id ?? repoId}</h1>
          <p>{repo?.repo_url ?? "Loading repository metadata..."}</p>
        </div>
        <Link className="button-link" to={`/repo/${repoId}/evals`}>
          Open evaluation dashboard
        </Link>
      </div>

      {repo && (
        <div className="metric-grid">
          <MetricCard label="Files indexed" value={String(repo.files_indexed)} />
          <MetricCard label="Chunks indexed" value={String(repo.chunks_indexed)} />
          <MetricCard
            label="Commit SHA"
            value={repo.commit_sha ? repo.commit_sha.slice(0, 12) : "n/a"}
          />
          <MetricCard label="Indexed at" value={new Date(repo.indexed_at).toLocaleString()} />
        </div>
      )}

      <article className="panel">
        <div className="panel__header">
          <h2>Ask RepoLens</h2>
          <span className="pill">POST /api/query</span>
        </div>
        <form className="form" onSubmit={handleQuery}>
          <label>
            Question
            <textarea
              rows={4}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              required
            />
          </label>
          <div className="form-row">
            <label>
              Retrieval mode
              <select
                value={retrievalMode}
                onChange={(event) => setRetrievalMode(event.target.value as RetrievalMode)}
              >
                <option value="hybrid">Hybrid</option>
                <option value="vector">Vector only</option>
                <option value="bm25">BM25 only</option>
              </select>
            </label>
            <label>
              Top K
              <input
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
              />
            </label>
          </div>
          <button type="submit" disabled={loading}>
            {loading ? "Querying..." : "Run grounded query"}
          </button>
        </form>
      </article>

      {error && <p className="error">{error}</p>}
      {result && <QueryResults result={result} />}
    </section>
  );
}

