# Base image：先從輕量的 Node image 開始，因為 Codex CLI 是用 npm 安裝的。
FROM node:22-bookworm-slim

# OCI metadata：幫 Docker tooling / registry 辨識這個 image。
LABEL org.opencontainers.image.title="cx-auth-export"
LABEL org.opencontainers.image.description="Disposable Codex auth export helper for cx account backups"

# Install runtime tools：這些是 image 執行時需要的基礎工具。
# - ca-certificates：HTTPS downloads / CA trust roots
# - git：有些 Codex workflows 會期待 git 存在
# - python3 + venv：把 cx 跑在 isolated virtual environment 裡
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       git \
       python3 \
       python3-pip \
       python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Install Codex CLI globally：讓 container 能執行 Codex device login。
RUN npm install -g @openai/codex

# /app 是 build workspace：先把專案複製進 image 裡再安裝。
WORKDIR /app

# 只 copy 安裝 / 執行 cx 需要的檔案，避免把整個 repo 都塞進 image。
COPY pyproject.toml README.md /app/
COPY src /app/src
COPY docker/auth-export/cx-auth-export-entrypoint.sh /usr/local/bin/cx-auth-export

# 建立 cx 的 virtual environment，安裝本專案，並準備 runtime directories。
RUN python3 -m venv /opt/cx-venv \
    && /opt/cx-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/cx-venv/bin/pip install --no-cache-dir /app \
    && chmod +x /usr/local/bin/cx-auth-export \
    && mkdir -p /out /work /root/.codex

# 把 virtual environment 放到 PATH 最前面，確保 `cx` 會用我們安裝的版本。
ENV PATH="/opt/cx-venv/bin:${PATH}"

# 讓 Codex state 留在 container 內，不要碰到 host 的 home directory。
ENV CODEX_HOME="/root/.codex"

# 預設工作目錄：container 啟動後落在 /work。
WORKDIR /work

# 預設 entrypoint：啟動 container 後直接跑 auth export helper。
ENTRYPOINT ["cx-auth-export"]
