FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

COPY backend /app/backend

RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -e /app/backend[full]

EXPOSE 8000

CMD ["uvicorn", "repolens.main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000"]

