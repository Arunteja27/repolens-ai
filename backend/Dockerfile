FROM python:3.11-slim

ARG BACKEND_EXTRAS=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY backend /app/backend

RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -e "/app/backend${BACKEND_EXTRAS}"

EXPOSE 8000

CMD ["uvicorn", "repolens.main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000"]
