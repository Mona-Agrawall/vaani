"""FastAPI server that exposes the translation pipeline one step at a time."""
import logging
import os
import re
import shutil
import time
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import pipeline

JOBS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs")
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
JOB_TTL_SECONDS = 24 * 60 * 60

log = logging.getLogger("uvicorn.error")
api = APIRouter(prefix="/api")


class Job(BaseModel):
    video_id: str


class SeparateJob(Job):
    keep_background: bool = False


class LanguageJob(Job):
    target_lang: str


class VoiceJob(LanguageJob):
    voice: Literal[pipeline.VOICE_GENDERS] = "female"


class MergeJob(Job):
    burn_subtitles: bool = True


class TranslationEdit(Job):
    texts: list[Annotated[str, Field(max_length=2000)]]


# ── helpers ──────────────────────────────────────────────
def job_dir(video_id):
    """Map a video_id to its job folder. Only canonical UUIDs are accepted,
    so a client can never make the server touch an arbitrary path."""
    try:
        video_id = str(uuid.UUID(video_id))
    except ValueError:
        raise HTTPException(400, "Invalid video_id") from None
    path = os.path.join(JOBS_DIR, video_id)
    if not os.path.isdir(path):
        raise HTTPException(404, "Video not found. Please upload it again.")
    return path


def remove_expired_jobs():
    if not os.path.isdir(JOBS_DIR):
        return
    cutoff = time.time() - JOB_TTL_SECONDS
    for entry in os.scandir(JOBS_DIR):
        if entry.is_dir() and entry.stat().st_mtime < cutoff:
            shutil.rmtree(entry.path, ignore_errors=True)


def send_file(video_id, name, missing_message, filename, extension, media_type):
    path = os.path.join(job_dir(video_id), name)
    if not os.path.isfile(path):
        raise HTTPException(404, missing_message)
    # Keep only safe filename characters so the value can't break the response header
    filename = re.sub(r"[^\w.\- ]", "_", os.path.basename(filename)).strip() or "translated"
    if not filename.lower().endswith(extension):
        filename += extension
    return FileResponse(path, media_type=media_type, filename=filename)


def run_step(step, video_id, *args):
    job = job_dir(video_id)
    pipeline.clear_outputs(job, step)
    try:
        return step(job, *args)
    except pipeline.PipelineError as error:
        pipeline.clear_outputs(job, step)
        raise HTTPException(400, str(error)) from error
    except Exception as error:
        pipeline.clear_outputs(job, step)
        log.exception("Step %s failed", step.__name__)
        raise HTTPException(500, f"{step.__name__} failed: {error}") from error


# ── routes ───────────────────────────────────────────────
# Plain `def` routes run in a thread pool, so long steps never block other requests.
@api.post("/upload")
def upload(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".mp4"):
        raise HTTPException(400, "Please upload an MP4 file.")
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Video is larger than 500 MB.")

    remove_expired_jobs()
    video_id = str(uuid.uuid4())
    job = os.path.join(JOBS_DIR, video_id)
    os.makedirs(job)
    with open(os.path.join(job, pipeline.VIDEO), "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"video_id": video_id}


@api.post("/extract-audio")
def extract_audio(job: Job):
    run_step(pipeline.extract_audio, job.video_id)
    return {"status": "done"}


@api.post("/separate")
def separate(job: SeparateJob):
    return {"kept": run_step(pipeline.separate, job.video_id, job.keep_background)}


@api.post("/transcribe")
def transcribe(job: Job):
    return {"sentences": run_step(pipeline.transcribe, job.video_id)}


@api.post("/translate")
def translate(job: LanguageJob):
    return {"sentences": run_step(pipeline.translate, job.video_id, job.target_lang)}


@api.put("/translation")
def edit_translation(edit: TranslationEdit):
    try:
        return {"sentences": pipeline.edit_translation(job_dir(edit.video_id), edit.texts)}
    except pipeline.PipelineError as error:
        raise HTTPException(400, str(error)) from error


@api.post("/synthesize")
def synthesize(job: VoiceJob):
    return {"voice": run_step(pipeline.synthesize, job.video_id, job.target_lang, job.voice)}


@api.post("/merge")
def merge(job: MergeJob):
    run_step(pipeline.merge, job.video_id, job.burn_subtitles)
    return {"status": "done"}


@api.get("/download/{video_id}")
def download(video_id: str, filename: str = "translated_video.mp4"):
    return send_file(video_id, pipeline.OUTPUT, "Translated video is not ready yet.",
                     filename, ".mp4", "video/mp4")


@api.get("/subtitles/{video_id}")
def subtitles(video_id: str, format: Literal["srt", "vtt"] = "srt", filename: str = "subtitles"):
    name, media_type = {
        "srt": (pipeline.SUBTITLES, "application/x-subrip"),
        "vtt": (pipeline.SUBTITLES_VTT, "text/vtt"),
    }[format]
    return send_file(video_id, name, "Subtitles are not ready yet.", filename, f".{format}", media_type)


app = FastAPI(title="Vaani")
app.include_router(api)

# In the single-container image (Hugging Face Spaces) the server also serves the built frontend.
# Mounted last, so /api routes take precedence.
if os.environ.get("FRONTEND_DIR"):
    app.mount("/", StaticFiles(directory=os.environ["FRONTEND_DIR"], html=True), name="frontend")
