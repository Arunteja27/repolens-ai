# RepoLens AI

RepoLens AI is a production-focused AI codebase onboarding assistant that ingests a repository, chunks and indexes source files, retrieves relevant code context, and answers questions with exact file and line citations.

## Security and Secrets

- No real API keys or secrets should ever be committed to this repository.
- `.env.example` contains placeholder variable names only. It does not contain usable credentials.
- Local secrets belong in an untracked `.env` file or in shell environment variables.
- For deployment, use a secret manager or platform-managed environment variables instead of hardcoding secrets.

## Cost Controls

- The current default local configuration is free/offline:
  - `EMBEDDING_PROVIDER=hashing`
  - `ANSWER_PROVIDER=extractive`
- Gemini or Vertex calls only happen if you explicitly provide `GEMINI_API_KEY` or `VERTEX_PROJECT_ID` and switch providers.
- Any paid-provider setup will be documented clearly before it is used.

## Status

The backend foundation and FastAPI wiring are in place. The frontend, tests, eval fixtures, Docker, CI, and the full project README are still being built out and will land in follow-up commits.
