# --- Stage 1: builder ---
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1-dev \
    curl \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first so they cache independently of source changes.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --prefix=/install .

# Fetch the latest static FFmpeg binary for the correct architecture.
ARG TARGETARCH
RUN FFMPEG_ARCH=$(case "${TARGETARCH}" in arm64) echo "arm64" ;; *) echo "amd64" ;; esac) \
    && curl -L "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-${FFMPEG_ARCH}-static.tar.xz" \
    -o ffmpeg.tar.xz \
    && tar -xf ffmpeg.tar.xz \
    && cp ffmpeg-*-static/ffmpeg /install/bin/ffmpeg \
    && cp ffmpeg-*-static/ffprobe /install/bin/ffprobe \
    && chmod +x /install/bin/ffmpeg /install/bin/ffprobe

# --- Stage 2: runtime ---
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

WORKDIR /app
COPY examples/ ./examples/

RUN useradd --create-home --shell /bin/bash beatsync \
    && mkdir -p /app/media /app/output \
    && chown -R beatsync:beatsync /app
USER beatsync

ENTRYPOINT ["python", "-m", "beatsync"]
CMD ["--config", "examples/drill.json"]
