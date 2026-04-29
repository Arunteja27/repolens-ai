// Builds the grounded answer prompt and forces file/line citations.
export function buildGroundedPrompt(question: string) {
  return [
    "Answer only from retrieved repository context.",
    "Cite exact files and line ranges.",
    question,
  ].join("\n");
}

