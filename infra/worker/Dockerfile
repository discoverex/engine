FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git python3 python3-pip python3-venv && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
COPY conf /app/conf
COPY infra /app/infra
COPY src /app/src

RUN UV_CACHE_DIR=/tmp/uv-cache uv python install 3.11
RUN UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON=3.11 uv sync --extra tracking --extra storage --extra ml-gpu

RUN chmod +x /app/infra/worker/entrypoint.sh

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app:/app/src"

ENTRYPOINT ["/app/infra/worker/entrypoint.sh"]
