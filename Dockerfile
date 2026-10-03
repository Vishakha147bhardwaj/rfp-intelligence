FROM python:3.11-slim

# System libraries OpenCV needs (OpenCV is used by the OCR package)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# uv, the package manager used by this project
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    FASTEMBED_CACHE_PATH=/models \
    HF_HOME=/models/hf

# Dependencies first (exact versions from uv.lock), then the code
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY config ./config
COPY eval ./eval
COPY ui ./ui
COPY .streamlit ./.streamlit
COPY main.py ./

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "python", "main.py", "serve", "--host", "0.0.0.0", "--port", "8000"]
