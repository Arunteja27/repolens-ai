// Reuses embeddings by chunk hash so unchanged chunks are not re-embedded.
const embeddingCache = new Map<string, number[]>();

export function getEmbedding(chunkHash: string) {
  return embeddingCache.get(chunkHash);
}

