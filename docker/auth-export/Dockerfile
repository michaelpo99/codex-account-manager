FROM node:22-bookworm-slim

LABEL org.opencontainers.image.title="cx-auth-export"
LABEL org.opencontainers.image.description="Disposable Codex auth export helper for cx account backups"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       git \
       python3 \
       python3-pip \
       python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @openai/codex

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY docker/auth-export/cx-auth-export-entrypoint.sh /usr/local/bin/cx-auth-export

RUN python3 -m venv /opt/cx-venv \
    && /opt/cx-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/cx-venv/bin/pip install --no-cache-dir /app \
    && chmod +x /usr/local/bin/cx-auth-export \
    && mkdir -p /out /work

ENV PATH="/opt/cx-venv/bin:${PATH}"
ENV CODEX_HOME="/tmp/codex"

WORKDIR /work

ENTRYPOINT ["cx-auth-export"]
