import { FormEvent, startTransition, useState } from "react";
import { useNavigate } from "react-router-dom";

import { indexRepo } from "../api";
import type { IndexRepoResponse } from "../types";

export function HomePage() {
  const navigate = useNavigate();
  const [repoUrl, setRepoUrl] = useState("https://github.com/openai/openai-cookbook");
  const [branch, setBranch] = useState("");
  const [result, setResult] = useState<IndexRepoResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const indexed = await indexRepo(repoUrl, branch);
      setResult(indexed);
      startTransition(() => {
        navigate(`/repo/${indexed.repo_id}`, { state: { repoUrl } });
      });
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "Indexing failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="home-grid">
      <article className="panel panel--hero">
        <span className="eyebrow">Production-ready AI infra portfolio project</span>
        <h1>Index any GitHub repo, retrieve grounded context, and answer with line-level citations.</h1>
        <p>
          RepoLens AI demonstrates repository ingestion, AST-aware chunking, embedding pipelines,
          vector and BM25 retrieval, evaluation harnesses, and operational telemetry in one stack.
        </p>
        <div className="hero-stats">
          <div>
            <strong>RAG</strong>
            <span>grounded answers from indexed code</span>
          </div>
          <div>
            <strong>Eval</strong>
            <span>recall, MRR, hallucination flags, latency</span>
          </div>
          <div>
            <strong>Ops</strong>
            <span>structured logs, metrics, cost awareness</span>
          </div>
        </div>
      </article>

      <article className="panel">
        <div className="panel__header">
          <h2>Index a repository</h2>
          <span className="pill">POST /api/repos/index</span>
        </div>
        <form className="form" onSubmit={handleSubmit}>
          <label>
            GitHub repository URL
            <input
              value={repoUrl}
              onChange={(event) => setRepoUrl(event.target.value)}
              placeholder="https://github.com/owner/repo"
              required
            />
          </label>
          <label>
            Branch override
            <input
              value={branch}
              onChange={(event) => setBranch(event.target.value)}
              placeholder="main"
            />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Indexing..." : "Index repository"}
          </button>
          {error && <p className="error">{error}</p>}
          {result && (
            <div className="success-box">
              <strong>{result.repo_id}</strong>
              <span>{result.files_indexed} files</span>
              <span>{result.chunks_indexed} chunks</span>
              <span>{result.duration_ms} ms</span>
            </div>
          )}
        </form>
      </article>
    </section>
  );
}

