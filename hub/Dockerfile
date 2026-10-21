# NexHub: Web-Oberfläche bauen, dann API + gebaute Seiten in ein Image.
# Bauen auf dem Server: nexhub-update <wer> <branch> (infra/server/usr/local/bin/nexhub-update)

FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json web/.npmrc ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv
RUN useradd --system --uid 10001 --home-dir /app nexhub
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY api/ ./
RUN uv sync --frozen --no-dev
COPY --from=web /web/build /app/web

# Stand des Codes für die System-Seite, z. B. "monorepo@71b65a2" (setzt nexhub-update)
ARG GIT_REV=dev
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 HUB_WEB_DIR=/app/web HUB_VERSION=$GIT_REV
USER nexhub
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["python", "-m", "nexhub_api"]
