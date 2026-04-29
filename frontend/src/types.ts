export type RetrievalMode = "vector" | "bm25" | "hybrid";

export interface IndexRepoResponse {
  repo_id: string;
  files_indexed: number;
  chunks_indexed: number;
  duration_ms: number;
}

export interface RepoRecord {
  repo_id: string;
  repo_url: string;
  branch?: string | null;
  commit_sha?: string | null;
  indexed_at: string;
  files_indexed: number;
  chunks_indexed: number;
  metadata: Record<string, unknown>;
}

export interface Citation {
  file_path: string;
  start_line: number;
  end_line: number;
}

export interface RetrievedChunk {
  id: string;
  repo_id: string;
  file_path: string;
  language: string;
  start_line: number;
  end_line: number;
  chunk_text: string;
  chunk_hash: string;
  symbol_name?: string | null;
  symbol_type?: string | null;
  score: number;
  source: string;
}

export interface TokenUsage {
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
}

export interface AnswerResponse {
  answer: string;
  citations: Citation[];
  retrieved_chunks: RetrievedChunk[];
  model_used: string;
  prompt_version: string;
  latency_ms: number;
  estimated_cost_usd?: number | null;
  token_usage?: TokenUsage | null;
  request_id: string;
}

export interface EvalItemResult {
  question: string;
  expected_files: string[];
  retrieved_files: string[];
  retrieval_hit_at_3: boolean;
  retrieval_hit_at_5: boolean;
  reciprocal_rank: number;
  answer_contains_score: number;
  groundedness_score: number;
  hallucination_flags: string[];
  latency_ms: number;
  estimated_cost_usd?: number | null;
  answer: string;
  citations: Citation[];
}

export interface EvalSummary {
  eval_id: string;
  repo_id: string;
  created_at: string;
  total_queries: number;
  retrieval_recall_at_3: number;
  retrieval_recall_at_5: number;
  mrr: number;
  answer_contains_score: number;
  groundedness_score: number;
  hallucination_flags: number;
  average_latency_ms: number;
  p95_latency_ms: number;
  average_cost_per_query: number;
  failure_rate: number;
  failed_items: EvalItemResult[];
}

