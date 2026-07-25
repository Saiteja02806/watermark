from __future__ import annotations

import base64
import hmac
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import settings
from .database.sqlite import initialize_database, recover_interrupted_jobs
from .models import RenderRequest, TrackRequest
from .routes import batches, masks, media, projects, rendering, tracking
from .services.process_service import process_supervisor
from .services.project_service import project_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.remote_access and not settings.access_password:
        raise RuntimeError(
            "LVC_PASSWORD is required when LVC_REMOTE_ACCESS=1."
        )
    initialize_database()
    for interrupted in recover_interrupted_jobs():
        project_id = interrupted["project_id"]
        job_type = interrupted["job_type"]
        try:
            if job_type == "NORMALIZE":
                process_supervisor.normalize(project_id)
            elif job_type == "TRACK":
                project_dir = project_service.path(project_id, "work")
                request_path = project_dir / "track_request.json"
                if not request_path.exists():
                    request_path = project_dir / "track_input.json"
                payload = json.loads(
                    request_path.read_text(encoding="utf-8")
                )
                process_supervisor.track(
                    project_id,
                    TrackRequest(
                        direction=payload.get("direction", "both"),
                        engine=payload.get("engine", "auto"),
                    ),
                )
            elif job_type == "RENDER":
                project_dir = project_service.path(project_id, "work")
                request_path = project_dir / "render_request.json"
                if not request_path.exists():
                    request_path = project_dir / "render_input.json"
                payload = json.loads(
                    request_path.read_text(encoding="utf-8")
                )
                process_supervisor.render(
                    project_id,
                    RenderRequest(
                        quality=payload.get("quality", "balanced"),
                        resolution=payload.get("resolution", "720p"),
                        maskExpansion=payload.get("maskExpansion", 4),
                        preserveAudio=payload.get("preserveAudio", True),
                        engine=payload.get("engine", "auto"),
                    ),
                )
        except Exception as exc:
            project_service.update(
                project_id,
                status="FAILED",
                error=f"Could not resume after server restart: {exc}",
            )
    yield


app = FastAPI(
    title="Local Video Cleaner",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=(
        ["*"]
        if settings.remote_access
        else ["127.0.0.1", "localhost", "testserver"]
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_control(request: Request, call_next):
    if settings.remote_access:
        authorization = request.headers.get("authorization", "")
        authenticated = False
        if authorization.lower().startswith("basic "):
            try:
                decoded = base64.b64decode(
                    authorization.split(" ", 1)[1], validate=True
                ).decode("utf-8")
                username, password = decoded.split(":", 1)
                authenticated = hmac.compare_digest(
                    username, settings.access_username
                ) and hmac.compare_digest(password, settings.access_password)
            except (ValueError, UnicodeDecodeError):
                authenticated = False
        if not authenticated:
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Frameclean"'},
            )
        return await call_next(request)

    client_host = request.client.host if request.client else ""
    if os.getenv("LVC_ALLOW_TEST_CLIENT") != "1" and client_host not in {
        "127.0.0.1",
        "::1",
        "localhost",
        "testclient",
    }:
        return JSONResponse(
            {"detail": "This application accepts local connections only."},
            status_code=403,
        )
    return await call_next(request)


@app.get("/api/health")
def health() -> dict:
    ffmpeg = settings.ffmpeg_path
    ffprobe = settings.ffprobe_path
    sam_ready = (
        settings.sam2_checkpoint.is_file()
        and (settings.root_dir / "vendor" / "sam2").is_dir()
        and settings.sam2_runtime_available
    )
    return {
        "status": "ok" if ffmpeg and ffprobe else "setup_required",
        "localOnly": not settings.remote_access,
        "ffmpeg": bool(ffmpeg),
        "ffprobe": bool(ffprobe),
        "sam2": sam_ready,
        "propainter": settings.propainter_available,
        "fallbackTracking": True,
        "fallbackInpainting": True,
        "limits": {
            "maximumDurationSeconds": settings.max_duration_seconds,
            "maximumProcessingLongEdge": settings.processing_long_edge,
            "selectedRegions": 1,
            "activeJobs": 1,
            "maximumBatchVideos": settings.max_batch_videos,
        },
    }


app.include_router(batches.router)
app.include_router(projects.router)
app.include_router(media.router)
app.include_router(masks.router)
app.include_router(tracking.router)
app.include_router(rendering.router)

web_dist = settings.root_dir / "apps" / "web" / "dist"
if web_dist.is_dir():
    assets = web_dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend(full_path: str) -> FileResponse:
        candidate = (web_dist / full_path).resolve()
        if web_dist.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(web_dist / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "apps.api.main:app",
        host=settings.bind_host,
        port=settings.port,
        reload=False,
    )
