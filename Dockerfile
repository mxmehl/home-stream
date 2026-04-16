# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

# --- Build stage ---
FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS builder

# Install build dependencies for packages with C extensions (uwsgi)
RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Compile bytecode for faster startup; copy mode for cache mount compatibility
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first (separate layer for better caching)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    uv sync --locked --no-dev --no-install-project

# Copy the project and install it
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# --- Runtime stage ---
FROM python:3.14-slim-trixie

# Create a group and user
RUN groupadd --gid 999 app && \
    useradd --uid 999 --gid app --shell /bin/bash --create-home app

WORKDIR /app

# Copy the virtual environment (with compiled bytecode) from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source (needed by uwsgi wsgi-file directive)
COPY . /app

# Activate the virtual environment via PATH
ENV PATH="/app/.venv/bin:$PATH"

RUN chown -R app:app /app
USER app

EXPOSE 8000
CMD ["uwsgi", "--ini", "uwsgi.docker.ini"]
