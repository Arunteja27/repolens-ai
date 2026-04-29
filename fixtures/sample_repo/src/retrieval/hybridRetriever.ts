// Combines vector similarity with BM25 scores using reciprocal rank fusion.
export function hybridRetrieve() {
  return {
    strategy: "rrf",
    signals: ["vector", "bm25"],
  };
}

