# Frameclean — fully local video object removal

Frameclean is a localhost-only React + FastAPI application for selecting one
unwanted region, reviewing its frame-aligned masks, reconstructing the covered
background, restoring the source audio, and exporting an H.264 MP4.

Media stays inside `data/projects/<random-uuid>/`. There are no accounts,
cloud-storage calls, remote inference APIs, analytics, or SaaS databases.

## What works now

- Local upload with sanitized filenames and UUID project folders.
- FFprobe inspection, orientation-aware 30 FPS normalization, 720p cap, editor
  proxy, and frame extraction.
- Auto Watermark detection for stable overlays, plus point, box, brush, and
  eraser input with resize-safe coordinate mapping.
- SAM 2.1 adapter in a separate Python 3.10 environment.
- OpenCV motion tracking fallback.
- A screen-fixed mask path for timestamps and accidental overlays that remain
  in the same frame coordinates.
- Mask review, manual correction, correction locking, suspicious-frame markers,
  dilation, and binary post-processing.
- ProPainter CUDA adapter with official weights, exact output sizing, and
  bounded temporal chunks for 6 GB GPUs.
- Structure-aware CPU fallback that preserves strong vertical/horizontal local
  texture instead of producing OpenCV's usual radial inpainting artifact.
- Original-audio muxing, output validation, real SSE job progress,
  cancellation, download, and permanent project deletion.
- Active-project restoration after a browser refresh.
- Working 480p/720p selection; output dimensions are validated before a project
  can be marked complete.
- Persistent multi-video batches with one relative watermark selection,
  per-video queue progress, sequential GPU execution, individual MP4 downloads,
  and one ZIP containing all completed results.
- An authenticated CUDA container and RunPod Pod template with persistent
  `/workspace` storage.

The CPU fallback is a correctness and simple-background path, not a promise of
ProPainter-level reconstruction on arbitrary motion, faces, hands, or large
occlusions.

## Verified local flow

The automated end-to-end test generates a short moving-object MP4 with audio,
then exercises:

`upload → normalize → extract 36 frames → track → write 36 masks → inpaint →
encode H.264 → restore AAC audio → download → delete project`

Run all checks:

```powershell
cmd /c npm run build
cmd /c npm run test:web
.\.venv\Scripts\python.exe -m pytest -q
```

## Quick start on this Windows workspace

Requirements:

- Node.js 20+
- Python 3.11 or 3.12 for the API
- NVIDIA GPU only for SAM 2.1 / ProPainter

Install and start:

```powershell
.\scripts\setup_windows.ps1
.\scripts\install_propainter_windows.ps1
.\scripts\start_local.ps1
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

The server is deliberately bound to `127.0.0.1`; do not change it to `0.0.0.0`
for normal use.

## How to remove a fixed overlay cleanly

1. Upload a clip up to 15 seconds.
2. Use **Auto Watermark** for a stable logo/text overlay, or choose **Box** /
   **Brush** and cover the complete visible mark, including its faint edge.
   A click alone is usually too small for a graphic overlay.
3. Enable **Keep mask fixed on screen** when the mark stays in one screen
   location.
4. Track the selection and inspect frames near the start, middle, and end.
5. Use 2–4 px expansion for a tight overlay mask.
6. Process the video and review the before/after result at full size.

## Batch workflow

1. Choose or drop two or more videos on the upload screen.
2. Wait until every valid clip says it is ready. A failed upload is isolated and
   does not block the remaining clips.
3. On any prepared reference clip, use **Auto Watermark**, or draw a tight box
   or brush mask around the watermark.
4. Leave **Use this position across the batch** enabled for a screen-fixed mark.
   Frameclean scales that relative location to each video's processing size.
5. Apply the selection. Fixed masks are generated for every valid clip.
6. Review the reference edge, choose 720p and ProPainter, then start the batch.
   Only one GPU-heavy export runs at a time; the rest remain visibly queued.
7. Download individual MP4s or a single ZIP after the queue finishes.

The shared-selection workflow is intended for repeated watermarks in the same
relative screen position. If one source has a different layout, open that item
from the queue and correct it before exporting.

The Track action remains disabled until a point, box, or painted mask exists, so
the backend cannot start with an empty prompt.

## Model environments

The API remains isolated from the GPU workers:

```text
API          Python 3.11/3.12  .venv
SAM 2.1      Python 3.10       .sam2-venv
ProPainter   Python 3.10       .propainter-venv
```

On this Windows installation, `.propainter-venv` is a small dependency overlay
that reuses the already verified CUDA PyTorch packages from `.sam2-venv`.
ProPainter's own scientific/video packages stay in the overlay.

Environment variables:

```text
LVC_SAM2_PYTHON
LVC_SAM2_CHECKPOINT
LVC_SAM2_CONFIG
LVC_PROPAINTER_PYTHON
LVC_PROPAINTER_REPO
LVC_TRACKER_ENGINE
LVC_INPAINTING_ENGINE
FFMPEG_PATH
FFPROBE_PATH
LVC_DATA_DIR
LVC_MAX_BATCH_VIDEOS
LVC_PROPAINTER_CHUNK_CORE_FRAMES
LVC_PROPAINTER_CHUNK_CONTEXT_FRAMES
LVC_REMOTE_ACCESS
LVC_USERNAME
LVC_PASSWORD
```

Defaults point to:

```text
.sam2-venv/Scripts/python.exe
.propainter-venv/Scripts/python.exe
models/sam2/sam2.1_hiera_small.pt
configs/sam2.1/sam2.1_hiera_s.yaml
vendor/ProPainter
```

The first release intentionally limits processing to one region, one active
GPU job, 15 seconds per clip, 720p, and MP4 H.264 output. A batch can contain up
to 20 clips by default.

## RunPod GPU Pod deployment

The interactive UI is packaged for a RunPod **GPU Pod**. It is intentionally not
packaged as a Serverless handler: browser uploads, interactive mask editing,
long progress sessions, and result downloads fit a persistent Pod web service
better.

Build and publish the Linux image:

```bash
docker build --platform linux/amd64 -t YOUR_DOCKERHUB_USER/frameclean:latest .
docker push YOUR_DOCKERHUB_USER/frameclean:latest
```

Create a custom RunPod template using
[`runpod-template.example.json`](runpod-template.example.json), or enter these
values in the console:

```text
Container image     YOUR_DOCKERHUB_USER/frameclean:latest
Container disk      30 GB
HTTP port           8000
Volume              100 GB or larger
Volume mount path   /workspace
GPU                 NVIDIA GPU, 16 GB minimum; 24 GB recommended
```

Required environment values:

```text
LVC_REMOTE_ACCESS=1
LVC_USERNAME=frameclean
LVC_PASSWORD=<a long random password>
LVC_DATA_DIR=/workspace/frameclean-data
LVC_INPAINTING_ENGINE=propainter
```

Expose `8000/http`. When the Pod is ready, open:

```text
https://<POD_ID>-8000.proxy.runpod.net
```

The browser will request the username and password configured above. Do not
deploy with an empty or reused password. The application refuses to start in
remote mode without `LVC_PASSWORD`.

RunPod GPUs with at least 22 GB VRAM automatically use larger 48-frame
ProPainter chunks with four context frames. Six GB GPUs keep the verified
10-frame/one-context profile. Override these only after a representative test:

```text
LVC_PROPAINTER_CHUNK_CORE_FRAMES=48
LVC_PROPAINTER_CHUNK_CONTEXT_FRAMES=4
LVC_PROPAINTER_NEIGHBOR_LENGTH=4
LVC_PROPAINTER_REF_STRIDE=20
LVC_PROPAINTER_SUBVIDEO_LENGTH=10
```

All originals, masks, SQLite state, and exports live under
`/workspace/frameclean-data`. A Pod volume survives stops/restarts while that
Pod lease exists; use a RunPod network volume if the data must survive deleting
and recreating the Pod. Container-disk data is not used for projects.

## WSL2 model setup

For the most supportable CUDA configuration, run the model workers under
Ubuntu 22.04 in WSL2:

```bash
bash scripts/install_wsl.sh
bash scripts/install_models.sh
```

Meta recommends Linux/WSL for SAM 2.1. ProPainter's published memory estimates
start around 6 GB for 640×480 FP16 at short sub-video lengths and around 7–8 GB
for 720×480. The Windows worker therefore uses FP16, four local neighbors,
short internal sub-videos, and overlapping outer chunks. This preserves a true
404×720 output without loading all 240 frames onto a 6 GB GPU at once.

## Storage and privacy

Each project contains the original, normalized proxy, frames, masks, logs, and
output under its UUID. `DELETE /api/projects/{id}` removes that entire UUID
folder after resolving and validating the exact path. No user-provided filename
is used as a directory name.

This project supports authorized cleanup of footage you are allowed to edit. It
does not include a specialized provenance- or authenticity-indicator bypass.

## Licensing

- SAM 2 source and checkpoints: Apache 2.0.
- ProPainter: NTU S-Lab noncommercial license; commercial use requires separate
  permission or a replacement with suitable terms.
