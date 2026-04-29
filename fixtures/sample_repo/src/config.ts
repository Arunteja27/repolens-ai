// Reads environment variables and keeps Gemini optional by default.
export const config = {
  answerProvider: process.env.ANSWER_PROVIDER ?? "extractive",
  embeddingProvider: process.env.EMBEDDING_PROVIDER ?? "sentence-transformers",
  geminiApiKey: process.env.GEMINI_API_KEY ?? "",
};

