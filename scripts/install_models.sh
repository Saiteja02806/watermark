#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v conda >/dev/null 2>&1; then
  echo "Conda is required for the isolated model environments." >&2
  exit 1
fi

ensure_conda_environment() {
  local name="$1"
  if ! conda run -n "$name" python --version >/dev/null 2>&1; then
    conda create -n "$name" python=3.10 -y
  fi
}

download_if_missing() {
  local url="$1"
  local target="$2"
  if [[ -s "$target" ]]; then
    echo "Using existing $(basename "$target")"
    return
  fi
  mkdir -p "$(dirname "$target")"
  local partial="${target}.partial"
  rm -f "$partial"
  curl -L --fail --retry 3 --retry-delay 2 "$url" -o "$partial"
  test -s "$partial"
  mv "$partial" "$target"
}

if [[ ! -d vendor/sam2 ]]; then
  git clone https://github.com/facebookresearch/sam2.git vendor/sam2
fi

ensure_conda_environment sam2
conda run -n sam2 python -m pip install \
  torch==2.7.1 torchvision==0.22.1 \
  --index-url https://download.pytorch.org/whl/cu128
SAM2_BUILD_CUDA=0 conda run -n sam2 python -m pip install -e vendor/sam2

download_if_missing \
  https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt \
  models/sam2/sam2.1_hiera_small.pt

if [[ ! -d vendor/ProPainter ]]; then
  git clone https://github.com/sczhou/ProPainter.git vendor/ProPainter
fi

ensure_conda_environment propainter
conda run -n propainter python -m pip install \
  torch==2.7.1 torchvision==0.22.1 \
  --index-url https://download.pytorch.org/whl/cu128
conda run -n propainter python -m pip install -r vendor/ProPainter/requirements.txt

for filename in raft-things.pth recurrent_flow_completion.pth ProPainter.pth; do
  download_if_missing \
    "https://github.com/sczhou/ProPainter/releases/download/v0.1.0/${filename}" \
    "vendor/ProPainter/weights/${filename}"
done

conda run -n propainter python -c \
  "import torch; assert torch.cuda.is_available(), 'CUDA is unavailable'; print('GPU:', torch.cuda.get_device_name(0)); print('PyTorch:', torch.__version__)"

echo "Model source, runtimes, checkpoints, and weights are ready."
echo "The application will auto-detect the sam2 and propainter Conda environments."
echo "Review the ProPainter noncommercial license before use."
