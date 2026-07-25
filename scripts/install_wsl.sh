#!/usr/bin/env bash
set -euo pipefail

sudo apt update
sudo apt install -y \
  git \
  ffmpeg \
  build-essential \
  ninja-build \
  pkg-config \
  libgl1 \
  libglib2.0-0

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "nvidia-smi is unavailable inside WSL. Fix the NVIDIA Windows driver/WSL GPU setup before installing models." >&2
  exit 1
fi

nvidia-smi

