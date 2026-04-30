# Personal Cloud Run Deployment

This guide is for the cheapest practical RepoLens deployment on Google Cloud.

It is meant for a personal demo, not a hardened public SaaS.

## What you are deploying

- `repolens-backend`: FastAPI API on Cloud Run
- `repolens-frontend`: static React app on Cloud Run via Nginx

The frontend will be reachable at a public `run.app` URL. The backend will also have its own `run.app` URL.

## Important limits of the cheap setup

- This path keeps AI costs at zero by using:
  - `EMBEDDING_PROVIDER=hashing`
  - `VECTOR_STORE_PROVIDER=memory`
  - `ANSWER_PROVIDER=extractive`
- Repo indexes are stored in the container filesystem under `.data/`.
- On Cloud Run, that storage is ephemeral. If the backend instance is restarted or a new revision is deployed, indexed repos can disappear and need to be re-indexed.

That means this setup is good for:

- your own demos
- showing the project on a public URL
- low-traffic personal use

It is not the right setup if you want durable indexes across restarts. For that, the next step would be a managed database/vector store.

## Cost strategy

To stay near the free tier:

- keep the default free local providers above
- use the default `run.app` URLs for now
- keep `min-instances=0`
- keep `max-instances=1`
- keep backend concurrency low
- keep Artifact Registry cleanup tight
- create a billing budget before deploying

Cloud Run has an always-free tier, but Google still requires billing to be enabled and usage above the free tier can be charged. Cloud Build and Artifact Registry can also create charges.

## 1. Create a Google Cloud project

In the Google Cloud console:

1. Create a new project, for example `repolens-personal`.
2. Link it to your billing account.
3. In `Billing -> Budgets & alerts`, create a small monthly budget.

Suggested budget for a personal demo:

- `$5/month`
- alerts at `20%`, `50%`, `90%`, and `100%`

## 2. Install and configure gcloud

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

Enable the services used by this deployment:

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

## 3. Create the Artifact Registry repository

Create one Docker repository in `us-central1`:

```bash
gcloud artifacts repositories create repolens \
  --repository-format=docker \
  --location=us-central1 \
  --description="RepoLens AI images"
```

You only need to do this once per project.

## 4. Build and deploy the backend

Build the backend image:

```bash
gcloud builds submit \
  --config cloudbuild.backend.yaml \
  --substitutions=_IMAGE_URI=us-central1-docker.pkg.dev/YOUR_PROJECT_ID/repolens/repolens-backend .
```

This personal deployment builds the backend with the base dependency set only. That keeps the image smaller, avoids optional parser/provider issues, and is enough for the cheap `hashing + memory + extractive` mode.

Deploy the backend:

```bash
gcloud run deploy repolens-backend \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/repolens/repolens-backend \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000 \
  --cpu 1 \
  --memory 512Mi \
  --concurrency 1 \
  --min-instances 0 \
  --max-instances 1 \
  --timeout 900 \
  --set-env-vars="EMBEDDING_PROVIDER=hashing,VECTOR_STORE_PROVIDER=memory,ANSWER_PROVIDER=extractive,RATE_LIMIT_ENABLED=true,RATE_LIMIT_QUERY_REQUESTS=60,RATE_LIMIT_QUERY_WINDOW_SECONDS=60,RATE_LIMIT_INDEX_REQUESTS=4,RATE_LIMIT_INDEX_WINDOW_SECONDS=3600,RATE_LIMIT_EVAL_REQUESTS=12,RATE_LIMIT_EVAL_WINDOW_SECONDS=3600,CORS_ALLOWED_ORIGINS=*"
```

Why these settings:

- `max-instances=1`: keeps spend and storage behavior predictable
- `concurrency=1`: only one request runs at a time, which is slower but safer for a personal app
- `timeout=900`: indexing larger repos can take a while
- `RATE_LIMIT_*`: built-in app-level throttling for the expensive endpoints
- `CORS_ALLOWED_ORIGINS=*`: simplest first deploy; you can tighten this after the frontend URL is known

After deploy, save the backend URL:

```text
https://repolens-backend-XXXXX-uc.a.run.app
```

## 5. Build and deploy the frontend

Build the frontend image:

```bash
gcloud builds submit \
  --config cloudbuild.frontend.yaml \
  --substitutions=_IMAGE_URI=us-central1-docker.pkg.dev/YOUR_PROJECT_ID/repolens/repolens-frontend .
```

Deploy the frontend:

```bash
gcloud run deploy repolens-frontend \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/repolens/repolens-frontend \
  --region us-central1 \
  --allow-unauthenticated \
  --port 80 \
  --cpu 1 \
  --memory 256Mi \
  --concurrency 20 \
  --min-instances 0 \
  --max-instances 1 \
  --set-env-vars="API_BASE_URL=https://repolens-backend-XXXXX-uc.a.run.app"
```

After deploy, save the frontend URL:

```text
https://repolens-frontend-XXXXX-uc.a.run.app
```

The frontend now reads the backend URL from a runtime-generated `/config.js` file, so changing the backend target only requires a frontend redeploy, not a rebuild.

## 6. Tighten backend CORS after the frontend exists

Redeploy the backend with the exact frontend origin:

```bash
gcloud run deploy repolens-backend \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/repolens/repolens-backend \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000 \
  --cpu 1 \
  --memory 512Mi \
  --concurrency 1 \
  --min-instances 0 \
  --max-instances 1 \
  --timeout 900 \
  --set-env-vars="EMBEDDING_PROVIDER=hashing,VECTOR_STORE_PROVIDER=memory,ANSWER_PROVIDER=extractive,RATE_LIMIT_ENABLED=true,RATE_LIMIT_QUERY_REQUESTS=60,RATE_LIMIT_QUERY_WINDOW_SECONDS=60,RATE_LIMIT_INDEX_REQUESTS=4,RATE_LIMIT_INDEX_WINDOW_SECONDS=3600,RATE_LIMIT_EVAL_REQUESTS=12,RATE_LIMIT_EVAL_WINDOW_SECONDS=3600,CORS_ALLOWED_ORIGINS=https://repolens-frontend-XXXXX-uc.a.run.app"
```

## 7. Verify the deployment

Backend:

- `https://repolens-backend-XXXXX-uc.a.run.app/health`
- `https://repolens-backend-XXXXX-uc.a.run.app/metrics`
- `https://repolens-backend-XXXXX-uc.a.run.app/api/repos/index`

Frontend:

- open `https://repolens-frontend-XXXXX-uc.a.run.app`
- open `https://repolens-frontend-XXXXX-uc.a.run.app/config.js`

End-to-end smoke test:

1. Open the frontend.
2. Index a public repo such as `https://github.com/Arunteja27/code-spa`.
3. Ask:
   - `Which file defines the ControlPanelProvider class?`
   - `Where are Code Spa settings declared?`
   - `Where is the Postgres schema defined?`
4. Confirm:
   - the first two answers cite real files
   - the Postgres question returns `I don't know from the indexed repo.`

## 8. What rate limiting is doing here

Cloud Run will autoscale, but it does not give you free built-in per-IP throttling by itself.

For this personal deployment, RepoLens now includes an in-memory backend rate limiter:

- `/api/query`: `60 requests / minute / IP`
- `/api/repos/index`: `4 requests / hour / IP`
- `/api/evals/run`: `12 requests / hour / IP`

This is intentionally simple and cheap:

- it works best with `max-instances=1`
- it is per instance, not globally shared across multiple instances
- it is enough for a personal demo without adding Cloud Armor

## 9. Why not custom domains yet

To stay simpler and cheaper, use the default `run.app` URLs first.

Cloud Run custom domains are possible, but Google’s docs show the recommended option is a global external Application Load Balancer, and Cloud Run domain mapping is still preview/limited. That is extra moving parts for a personal demo.

## 10. What can still cost money

Even on the cheap path, these can create charges:

- Cloud Run compute if usage goes past the free tier
- Cloud Build if you burn through the monthly free build minutes
- Artifact Registry storage over the free allowance
- network egress beyond the small free amount

These will definitely add cost if you turn them on later:

- Gemini API beyond free limits
- Vertex AI
- Cloud SQL / managed persistence
- Cloud Armor / external load balancers

## 11. Cleanup if you want to stop spending

Delete the two services:

```bash
gcloud run services delete repolens-backend --region us-central1
gcloud run services delete repolens-frontend --region us-central1
```

Delete the Artifact Registry repository if you are done with it:

```bash
gcloud artifacts repositories delete repolens --location us-central1
```

You can also disable billing on the project if you want a hard stop.
