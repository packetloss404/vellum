# Multi-platform index digest recorded 2026-09-04. Dependabot proposes digest
# updates while deployments remain reproducible between updates.
FROM python:3.15.0-slim@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58

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
