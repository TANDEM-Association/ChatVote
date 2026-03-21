# syntax=docker/dockerfile:1

# ── Base: Ubuntu with system packages ───────────────────────────────────────────
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# System packages + Python 3.12 in a single cached layer
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git make jq \
    python3.12 python3.12-dev python3.12-venv python3-pip

# Poetry (installed directly — avoids broken shebangs from multi-stage COPY)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --break-system-packages poetry && \
    poetry config virtualenvs.in-project true

# Pre-create cache dirs owned by vscode (features install as root,
# post-create runs as vscode)
RUN mkdir -p /home/vscode/.cache/node/corepack \
             /home/vscode/.npm \
             /home/vscode/.local/share/pnpm \
             /home/vscode/.cache/pypoetry \
    && chown -R vscode:vscode /home/vscode/.cache /home/vscode/.npm \
                              /home/vscode/.local
