FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GRIDPULSE_ENV=production

WORKDIR /app
RUN addgroup --system --gid 10001 gridpulse \
    && adduser --system --uid 10001 --ingroup gridpulse --home /nonexistent gridpulse \
    && mkdir -p /data \
    && chown 10001:10001 /data

COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
RUN pip install --no-cache-dir .

USER 10001:10001
EXPOSE 8000
# Honor PORT on hosted platforms while retaining the local Docker default.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health', timeout=2).read()" || exit 1

CMD ["sh", "-c", "exec uvicorn gridpulse.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
