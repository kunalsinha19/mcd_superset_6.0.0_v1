# syntax=docker/dockerfile:1
#
# Single-stage build. The frontend is NOT built here -- superset/static/assets/
# already contains the production webpack output checked into this repo, so
# no Node.js toolchain is needed in the image at all.
#
# Dependency versions are pinned via requirements-lock.txt, frozen from the
# exact environment this codebase was fixed and verified against (Python
# 3.13.5). Installing from pyproject.toml's own loose ranges instead would
# risk re-resolving newer package versions and reintroducing the SQLAlchemy
# 2.0 / Flask-SQLAlchemy 3.x / WTForms 3.x compatibility issues that were
# fixed in this codebase -- do not swap this out for a plain `pip install .`
# without re-verifying the app still boots.

FROM python:3.13-slim-bookworm AS base

# Build deps for packages that compile native extensions (psycopg2,
# cryptography, pillow, etc.). Kept in the final image intentionally --
# multi-stage build isn't worth it here since most of these libs are
# also needed at runtime by the packages that link against them.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libsasl2-dev \
        libldap2-dev \
        libssl-dev \
        libffi-dev \
        zlib1g-dev \
        libjpeg-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash superset

WORKDIR /app

# Install pinned Python dependencies first so this layer caches independently
# of application source changes.
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt

# Copy application source (respects .dockerignore -- no node_modules,
# no .git, no __pycache__, superset_config.py excluded).
COPY . .

# Install the app itself without letting pip re-resolve dependencies
# (already installed above from the lock file).
RUN pip install --no-cache-dir --no-deps -e .

COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

RUN mkdir -p /app/superset_home && chown -R superset:superset /app
USER superset

ENV SUPERSET_HOME=/app/superset_home \
    FLASK_APP=superset.app:create_app \
    PYTHONUNBUFFERED=1

EXPOSE 8088

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8088/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8088", \
     "--workers", "4", \
     "--worker-class", "gthread", \
     "--threads", "4", \
     "--timeout", "120", \
     "--limit-request-line", "0", \
     "superset.app:create_app()"]
