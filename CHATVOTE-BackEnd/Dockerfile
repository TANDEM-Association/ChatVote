# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

FROM python:3.11.3-slim

# Install system dependencies for Playwright browsers
RUN apt-get update && apt-get install -y \
    # Build tools (needed by hdbscan, numpy C extensions)
    build-essential \
    # Playwright dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Install Poetry
RUN pip install poetry

# Copy only the necessary files for Poetry (to leverage Docker layer caching)
COPY pyproject.toml poetry.lock /app/

WORKDIR /app

# Configure poetry to not create virtual env (use system python)
RUN poetry config virtualenvs.create false

# Install dependencies (production only)
# Use pip installer backend to avoid nvidia namespace __init__.py conflicts
RUN poetry config installer.modern-installation false && \
    poetry install --no-root --only main

# Replace PyTorch with CPU-only build if no CUDA available (~200MB vs ~2GB)
# Override with: docker build --build-arg TORCH_VARIANT=gpu .
ARG TORCH_VARIANT=auto
RUN if [ "$TORCH_VARIANT" = "auto" ]; then \
      if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then \
        echo "CUDA detected — keeping GPU-enabled PyTorch"; \
      else \
        echo "WARNING: No CUDA/GPU detected — replacing with CPU-only PyTorch (saves ~1.8GB)"; \
        pip install torch --index-url https://download.pytorch.org/whl/cpu; \
      fi; \
    elif [ "$TORCH_VARIANT" = "cpu" ]; then \
      echo "Replacing with CPU-only PyTorch (TORCH_VARIANT=cpu)"; \
      pip install torch --index-url https://download.pytorch.org/whl/cpu; \
    fi

# Install Playwright browsers (Chromium only for smaller image)
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy the rest of the application code and optional Firebase credentials
# This will include files like:
# - chat-vote-dev-firebase-adminsdk-fbsvc-5357066618.json
# if they are present in the project root.
# If these files are absent, Google Application Default Credentials must be provided when running the container
COPY . /app

CMD ["python", "-m", "src.aiohttp_app", "--host", "0.0.0.0", "--port", "8080"]
