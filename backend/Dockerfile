# Multi-platform index digest recorded 2026-09-04. Dependabot proposes digest
# updates while deployments remain reproducible between updates.
FROM python:3.14.0-slim@sha256:0aecac02dc3d4c5dbb024b753af084cafe41f5416e02193f1ce345d671ec966e

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
