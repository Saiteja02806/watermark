# syntax=docker/dockerfile:1.7

FROM node:20-bookworm-slim AS web-build
WORKDIR /src
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci
COPY apps/web apps/web
RUN npm run build

FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime

ARG SAM2_COMMIT=2b90b9f5ceec907a1c18123530e92e794ad901a4
ARG PROPAINTER_COMMIT=e870e79321c31b733e2031af5aa2fb1fe3ac7eec
ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    LVC_BIND_HOST=0.0.0.0 \
    LVC_PORT=8000 \
    LVC_REMOTE_ACCESS=1 \
    LVC_USERNAME=frameclean \
    LVC_DATA_DIR=/workspace/frameclean-data \
    LVC_SAM2_PYTHON=python \
    LVC_PROPAINTER_PYTHON=python \
    LVC_SAM2_CHECKPOINT=/app/models/sam2/sam2.1_hiera_small.pt \
    LVC_PROPAINTER_REPO=/app/vendor/ProPainter \
    MPLCONFIGDIR=/tmp/matplotlib

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        git \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY apps/api/requirements.txt /tmp/api-requirements.txt
RUN python -m pip install -r /tmp/api-requirements.txt \
    && python -m pip install \
        av \
        addict \
        einops \
        future \
        scipy \
        matplotlib \
        scikit-image \
        imageio-ffmpeg \
        imageio \
        pyyaml \
        requests \
        timm \
        yapf

RUN git clone https://github.com/facebookresearch/sam2.git vendor/sam2 \
    && git -C vendor/sam2 checkout "${SAM2_COMMIT}" \
    && SAM2_BUILD_CUDA=0 python -m pip install -e vendor/sam2 \
    && git clone https://github.com/sczhou/ProPainter.git vendor/ProPainter \
    && git -C vendor/ProPainter checkout "${PROPAINTER_COMMIT}"

RUN mkdir -p models/sam2 vendor/ProPainter/weights \
    && curl -L --fail --retry 3 \
        https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt \
        -o models/sam2/sam2.1_hiera_small.pt \
    && for filename in raft-things.pth recurrent_flow_completion.pth ProPainter.pth; do \
        curl -L --fail --retry 3 \
          "https://github.com/sczhou/ProPainter/releases/download/v0.1.0/${filename}" \
          -o "vendor/ProPainter/weights/${filename}"; \
       done

COPY apps/api apps/api
COPY workers workers
COPY scripts/start_container.sh scripts/start_container.sh
COPY scripts/container_healthcheck.py scripts/container_healthcheck.py
COPY --from=web-build /src/apps/web/dist apps/web/dist

RUN chmod +x scripts/start_container.sh \
    && mkdir -p /workspace/frameclean-data /tmp/matplotlib

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=8s --start-period=30s --retries=3 \
  CMD ["python", "/app/scripts/container_healthcheck.py"]

ENTRYPOINT ["/app/scripts/start_container.sh"]
