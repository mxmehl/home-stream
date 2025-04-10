# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

FROM python:3.13-slim AS base

ENV PATH="$PATH:/root/.local/bin"
EXPOSE 8000

# Install required Python packages
RUN pip install --no-cache-dir pipx && \
    pipx install --global poetry && \
    pipx ensurepath

# Make poetry create venv in /app/.venv
RUN poetry config virtualenvs.in-project true

WORKDIR /app

FROM base AS build

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential

# Add relevant python files for installing project
COPY pyproject.toml poetry.lock README.md /app/
COPY home_stream /app/home_stream

RUN poetry install --without dev

FROM base AS runtime

# Create a group and user
RUN groupadd --gid 999 app && \
    useradd --uid 999 --gid app --shell /bin/bash --create-home app

COPY --from=build /app/.venv /app/.venv
COPY . /app
RUN chown -R app:app /app
USER app

CMD ["poetry", "run", "uwsgi", "--ini", "uwsgi.docker.ini"]
