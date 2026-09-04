# Multi-platform index digest recorded 2026-09-04. Dependabot proposes digest
# updates while deployments remain reproducible between updates.
FROM python:3.12.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c

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
