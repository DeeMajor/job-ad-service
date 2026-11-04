# job-ad-service — headless drafting + scoring API
FROM python:3.10-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN pip install --no-cache-dir uv && useradd --create-home --uid 10001 app
WORKDIR /app

# dependencies first (cached layer), then the code
COPY pyproject.toml README.md ./
RUN uv pip install --system --no-cache "anthropic>=1" "pydantic>=2" fastapi "uvicorn[standard]" pyyaml httpx redis prometheus-client scikit-learn pandas numpy

COPY job_ad ./job_ad
COPY docs/job-ad-drafter/metrics ./docs/job-ad-drafter/metrics
COPY docs/job-ad-drafter/openapi.json ./docs/job-ad-drafter/openapi.json
COPY docs/shortlist-ranker/ranking-spec.yaml ./docs/shortlist-ranker/ranking-spec.yaml
COPY docs/offer-contract-drafter/compliance-rules.yaml ./docs/offer-contract-drafter/compliance-rules.yaml

USER app
EXPOSE 4310
ENV PORT=4310 LOG_LEVEL=INFO ENRICH_ENABLED=false MAX_CONCURRENT_DRAFTS=4 DAILY_SPEND_CAP_USD=20
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:4310/healthz', timeout=4).status==200 else 1)"
CMD ["sh", "-c", "uvicorn job_ad.api.app:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 120 --log-level warning"]
