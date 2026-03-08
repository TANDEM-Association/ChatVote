# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

# ── Prebuilt base with all deps + Playwright/Chromium ───────────────
# Rebuild base only when poetry.lock changes:
#   docker build -f Dockerfile.base -t rg.fr-par.scw.cloud/chatvote/backend-base:latest .
#   docker push rg.fr-par.scw.cloud/chatvote/backend-base:latest
FROM rg.fr-par.scw.cloud/chatvote/backend-base:latest

WORKDIR /app
COPY . /app

CMD ["python", "-m", "src.aiohttp_app", "--host", "0.0.0.0", "--port", "8080"]

# triggered deploy
