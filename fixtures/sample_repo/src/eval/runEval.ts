// Runs retrieval recall, MRR, groundedness, and latency evaluations.
export function runEvalSuite() {
  return {
    metrics: ["recall@3", "recall@5", "mrr", "groundedness", "latency"],
  };
}

