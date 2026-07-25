#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v conda >/dev/null 2>&1; then
  echo "Conda is required for the isolated model environments." >&2
  exit 1
fi

if [[ ! -d vendor/sam2 ]]; then
  git clone https://github.com/facebookresearch/sam2.git vendor/sam2
fi

conda create -n sam2 python=3.10 -y
conda run -n sam2 python -m pip install \
  torch==2.5.1 torchvision==0.20.1 \
  --index-url https://download.pytorch.org/whl/cu121
SAM2_BUILD_CUDA=0 conda run -n sam2 python -m pip install -e vendor/sam2

mkdir -p models/sam2
curl -L \
  https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt \
  -o models/sam2/sam2.1_hiera_small.pt

if [[ ! -d vendor/ProPainter ]]; then
  git clone https://github.com/sczhou/ProPainter.git vendor/ProPainter
fi

conda create -n propainter python=3.8 -y
conda run -n propainter python -m pip install -r vendor/ProPainter/requirements.txt

echo "Model source and environments are installed."
echo "Review the ProPainter noncommercial license before use."

