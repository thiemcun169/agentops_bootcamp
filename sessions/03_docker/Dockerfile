# syntax=docker/dockerfile:1
# Multi-stage build: uv and the build cache stay in "build"; "runtime" gets only the app and its .venv.

# uv as a pinned image, copied in below (no pip install uv)
FROM ghcr.io/astral-sh/uv:0.13.6 AS uv

FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS build
COPY --from=uv /uv /uvx /bin/
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_NO_DEV=1 UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# 1) dependencies only: this layer is rebuilt only when pyproject.toml or uv.lock change
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project
# 2) the code: a code change rebuilds from here
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS runtime
RUN groupadd --system app && useradd --system -g app app
WORKDIR /app
COPY --from=build --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER app
EXPOSE 8000
# liveness only: the slim image has no curl, Python is already there
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request as r; r.urlopen('http://127.0.0.1:8000/health', timeout=4)"]
# exec form: fastapi is PID 1 and receives SIGTERM from docker stop
CMD ["fastapi", "run"]
