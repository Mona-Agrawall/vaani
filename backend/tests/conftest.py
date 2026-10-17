import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
import pipeline  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    """An API client whose job folders live in a temporary directory."""
    monkeypatch.setattr(main, "JOBS_DIR", str(tmp_path))
    return TestClient(main.app)


@pytest.fixture
def make_job(tmp_path):
    """Create a job folder (as an upload would) and return (video_id, path)."""
    def make(video_id="3f2b8c1e-0000-4000-8000-000000000001"):
        path = tmp_path / video_id
        path.mkdir()
        return video_id, str(path)
    return make


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def make_video(path, seconds=6, audio=True):
    """A small test video: colour bars plus, optionally, a 440 Hz tone."""
    inputs = ["-f", "lavfi", "-i", f"testsrc=size=320x240:rate=25:duration={seconds}"]
    if audio:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    ffmpeg(*inputs, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path))


def write_json(job, name, data):
    with open(os.path.join(job, name), "w", encoding="utf-8") as f:
        json.dump(data, f)


def probe(path, entries="stream=codec_type:format=duration"):
    return subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout


__all__ = ["pipeline", "make_video", "write_json", "probe", "ffmpeg"]
