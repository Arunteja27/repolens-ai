# Cloud Run Deployment

RepoLens AI can be deployed as two services:

1. `repolens-backend` on Cloud Run for the FastAPI API.
2. `repolens-frontend` on Cloud Run for the Vite-built static UI served through Nginx.

## 1. Prepare Google Cloud

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
```

## 2. Build and push the backend image

```bash
gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/repolens/repolens-backend -f backend/Dockerfile .
```

Deploy it:

```bash
gcloud run deploy repolens-backend \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/repolens/repolens-backend \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars EMBEDDING_PROVIDER=hashing,VECTOR_STORE_PROVIDER=memory,ANSWER_PROVIDER=extractive
```

Notes:

- The fully free/demo path uses `hashing` embeddings and `extractive` answers.
- If you switch to Gemini or Vertex, that can incur usage charges.
- Local Chroma storage on Cloud Run is ephemeral. For persistent production retrieval, move metadata to managed storage and replace the vector layer with pgvector or Vertex AI Vector Search.

## 3. Build and push the frontend image

First capture the backend URL from the prior step, then build with it:

```bash
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/repolens/repolens-frontend \
  --build-arg VITE_API_BASE_URL=https://YOUR_BACKEND_URL \
  -f frontend/Dockerfile .
```

Deploy it:

```bash
gcloud run deploy repolens-frontend \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/repolens/repolens-frontend \
  --region us-central1 \
  --allow-unauthenticated
```

## 4. Secret handling

- Never bake API keys into images.
- For Gemini direct API usage, store `GEMINI_API_KEY` in Secret Manager and mount it into Cloud Run as an environment variable.
- For Vertex AI, prefer workload identity and service-account-based auth over static credentials.

## 5. Recommended production follow-ups

- Replace `VECTOR_STORE_PROVIDER=memory` with `chroma` for local persistence or pgvector for managed persistence.
- Add a managed database for repo metadata and eval records.
- Restrict CORS to your deployed frontend origin.
- Add request auth before exposing private repository indexing.

