# FastAPI backend image (app/). Wired with postgres/grafana via docker-compose.yml;
# LLM calls go to Amazon Bedrock (external).
FROM python:3.11-slim AS base

WORKDIR /srv

# System deps needed to build a couple of the ML/psycopg2 wheels on slim.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# CPU inference is sufficient for MiniLM; avoid downloading NVIDIA GPU libraries.
RUN pip install --no-cache-dir torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
# datasets 2.18 uses the older Arrow API and this stack pins NumPy 1.x.
RUN pip install --no-cache-dir pyarrow==16.1.0

COPY app/ ./app/
COPY domains/ ./domains/
COPY seed_kb.py ./

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
