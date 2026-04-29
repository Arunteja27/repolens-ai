import type { AnswerResponse } from "../types";

interface QueryResultsProps {
  result: AnswerResponse;
}

export function QueryResults({ result }: QueryResultsProps) {
  return (
    <section className="results-grid">
      <article className="panel panel--answer">
        <div className="panel__header">
          <h2>Answer</h2>
          <span className="pill">{result.model_used}</span>
        </div>
        <pre className="answer-block">{result.answer}</pre>
        <div className="citation-list">
          {result.citations.map((citation) => (
            <span key={`${citation.file_path}:${citation.start_line}`} className="citation-chip">
              {citation.file_path}:{citation.start_line}-{citation.end_line}
            </span>
          ))}
        </div>
      </article>

      <article className="panel">
        <div className="panel__header">
          <h2>Request telemetry</h2>
          <span className="pill">{result.request_id}</span>
        </div>
        <dl className="definition-grid">
          <div>
            <dt>Latency</dt>
            <dd>{result.latency_ms} ms</dd>
          </div>
          <div>
            <dt>Prompt version</dt>
            <dd>{result.prompt_version}</dd>
          </div>
          <div>
            <dt>Estimated cost</dt>
            <dd>{formatCurrency(result.estimated_cost_usd)}</dd>
          </div>
          <div>
            <dt>Total tokens</dt>
            <dd>{result.token_usage?.total_tokens ?? "n/a"}</dd>
          </div>
        </dl>
      </article>

      <article className="panel panel--full">
        <div className="panel__header">
          <h2>Retrieved chunks</h2>
          <span className="pill">{result.retrieved_chunks.length} chunks</span>
        </div>
        <div className="chunks">
          {result.retrieved_chunks.map((chunk) => (
            <details key={chunk.id} className="chunk-card">
              <summary>
                <div>
                  <strong>{chunk.file_path}</strong>
                  <small>
                    {chunk.start_line}-{chunk.end_line} • {chunk.source} • {chunk.language}
                  </small>
                </div>
                <span className="score">{chunk.score.toFixed(4)}</span>
              </summary>
              <pre>{chunk.chunk_text}</pre>
            </details>
          ))}
        </div>
      </article>
    </section>
  );
}

function formatCurrency(value?: number | null): string {
  if (value == null) {
    return "n/a";
  }
  return `$${value.toFixed(4)}`;
}

