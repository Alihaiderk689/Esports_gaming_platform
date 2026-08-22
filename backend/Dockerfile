FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# rag_chat.views imports embedding_service and rerank_service at module
# import time, which load SentenceTransformer('all-MiniLM-L6-v2') and
# CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2') eagerly. Pre-download
# both into the image now, while network access is still available, so
# gunicorn workers never hit HuggingFace Hub at runtime. HF_HUB_OFFLINE is
# set *after* this step — setting it earlier would block the very download
# it's meant to make unnecessary.
RUN python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('all-MiniLM-L6-v2'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"
ENV HF_HUB_OFFLINE=1

COPY . .

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R appuser:appuser /app "$HF_HOME"
USER appuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
# --workers 1: each worker loads its own full copy of rag_chat's eagerly-loaded
# sentence-transformers embedding + reranking models (see the RUN step above) —
# on a 512MB instance, 3 workers x that footprint is what was causing OOM kills
# under real load. Bump this only alongside a larger instance size.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "120"]
