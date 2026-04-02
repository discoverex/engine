FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /bin/uv

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app:/app/src \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        libglib2.0-0 \
        libxcb1 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
    --frozen \
    --no-dev \
    --no-install-project \
    --managed-python \
    --python 3.11 \
    --extra tracking \
    --extra storage \
    --extra ml-gpu \
    --extra validator

COPY prefect_flow.py /app/prefect_flow.py
COPY conf /app/conf
COPY delivery /app/delivery
COPY infra /app/infra
COPY src /app/src

RUN chmod +x /app/infra/worker/entrypoint.sh

ENTRYPOINT ["/app/infra/worker/entrypoint.sh"]
