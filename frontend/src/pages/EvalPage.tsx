import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getLatestEval, runEval } from "../api";
import { MetricCard } from "../components/MetricCard";
import type { EvalSummary } from "../types";

export function EvalPage() {
  const { repoId = "" } = useParams();
  const [evalSummary, setEvalSummary] = useState<EvalSummary | null>(null);
  const [evalPath, setEvalPath] = useState("evals/sample_eval.json");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getLatestEval(repoId)
      .then(setEvalSummary)
      .catch(() => {
        return;
      });
  }, [repoId]);

  async function handleRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const summary = await runEval(repoId, evalPath);
      setEvalSummary(summary);
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Eval run failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="stack">
      <div className="page-header">
        <div>
          <span className="eyebrow">Evaluation harness</span>
          <h1>Repo evaluation dashboard</h1>
          <p>Measure retrieval recall, answer quality, hallucination risk, latency, and cost.</p>
        </div>
        <Link className="button-link" to={`/repo/${repoId}`}>
          Back to repo queries
        </Link>
      </div>

      <article className="panel">
        <div className="panel__header">
          <h2>Run eval set</h2>
          <span className="pill">POST /api/evals/run</span>
        </div>
        <form className="form" onSubmit={handleRun}>
          <label>
            Eval set path
            <input value={evalPath} onChange={(event) => setEvalPath(event.target.value)} />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Running..." : "Run evaluation"}
          </button>
        </form>
      </article>

      {error && <p className="error">{error}</p>}

      {evalSummary && (
        <>
          <div className="metric-grid">
            <MetricCard label="Recall@3" value={formatPct(evalSummary.retrieval_recall_at_3)} />
            <MetricCard label="Recall@5" value={formatPct(evalSummary.retrieval_recall_at_5)} />
            <MetricCard label="MRR" value={evalSummary.mrr.toFixed(3)} />
            <MetricCard
              label="Answer match"
              value={formatPct(evalSummary.answer_contains_score)}
            />
            <MetricCard label="Groundedness" value={formatPct(evalSummary.groundedness_score)} />
            <MetricCard
              label="Hallucination rate"
              value={formatPct(evalSummary.hallucination_rate)}
            />
            <MetricCard
              label="Avg latency"
              value={`${Math.round(evalSummary.average_latency_ms)} ms`}
            />
            <MetricCard label="P95 latency" value={`${Math.round(evalSummary.p95_latency_ms)} ms`} />
            <MetricCard label="Avg cost" value={`$${evalSummary.average_cost_per_query.toFixed(4)}`} />
            <MetricCard label="Failure rate" value={formatPct(evalSummary.failure_rate)} />
          </div>

          <article className="panel panel--full">
            <div className="panel__header">
              <h2>Failed evals</h2>
              <span className="pill">{evalSummary.failed_items.length} items</span>
            </div>
            <div className="failed-table">
              {evalSummary.failed_items.map((item) => (
                <article className="failure-card" key={item.question}>
                  <strong>{item.question}</strong>
                  <p>Expected: {item.expected_files.join(", ") || "n/a"}</p>
                  <p>Retrieved: {item.retrieved_files.join(", ") || "n/a"}</p>
                  <p>Flags: {item.hallucination_flags.join(", ") || "none"}</p>
                </article>
              ))}
              {evalSummary.failed_items.length === 0 && <p>No failed evals in the latest run.</p>}
            </div>
          </article>
        </>
      )}
    </section>
  );
}

function formatPct(value: number): string {
  return `${Math.round(value * 100)}%`;
}
