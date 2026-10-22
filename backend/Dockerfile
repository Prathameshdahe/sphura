FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data \
    FASTEMBED_CACHE_PATH=/app/data/fastembed_cache \
    PORT=8000

# libgl/libglib are needed by the OCR engine (rapidocr → opencv)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY ml ./ml

RUN useradd --create-home --uid 10001 sphura && mkdir -p /app/data && chown -R sphura /app
USER sphura

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD curl -fsS "http://localhost:${PORT}/api/health" || exit 1

# PORT is set by the host (Render: 10000, Hugging Face Spaces: 7860); behind their proxy the client IP and
# https scheme come from X-Forwarded-* headers.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*' --timeout-keep-alive 75"]
