# Multi-platform index digest recorded 2026-09-04. Dependabot proposes digest
# updates while deployments remain reproducible between updates.
FROM python:3.14.8-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.lock ./requirements.lock
RUN pip install --require-hashes --no-deps -r requirements.lock

COPY backend/pyproject.toml ./pyproject.toml
COPY backend/vellum ./vellum

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin vellum
USER vellum

EXPOSE 8731

CMD ["uvicorn", "vellum.main:app", "--host", "0.0.0.0", "--port", "8731", "--proxy-headers", "--forwarded-allow-ips", "*"]
