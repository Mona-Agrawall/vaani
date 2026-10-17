"""API tests: validation, error mapping, downloads and job lifecycle. Pipeline steps are faked."""
import os
import time

from conftest import write_json

import main
import pipeline as p

UNKNOWN = "00000000-0000-4000-8000-000000000000"


# ── upload ───────────────────────────────────────────────
def test_upload_creates_a_job(client, tmp_path):
    response = client.post("/api/upload", files={"file": ("clip.mp4", b"fake video", "video/mp4")})
    assert response.status_code == 200
    video_id = response.json()["video_id"]
    assert (tmp_path / video_id / p.VIDEO).read_bytes() == b"fake video"


def test_upload_rejects_other_formats(client):
    response = client.post("/api/upload", files={"file": ("clip.mov", b"x", "video/quicktime")})
    assert response.status_code == 400


def test_upload_rejects_large_files(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 5)
    response = client.post("/api/upload", files={"file": ("clip.mp4", b"0123456789", "video/mp4")})
    assert response.status_code == 413


def test_expired_jobs_are_removed_on_upload(client, make_job):
    _, old = make_job()
    stale = time.time() - main.JOB_TTL_SECONDS - 60
    os.utime(old, (stale, stale))
    client.post("/api/upload", files={"file": ("clip.mp4", b"x", "video/mp4")})
    assert not os.path.exists(old)


# ── job lookup ───────────────────────────────────────────
def test_video_ids_must_be_uuids(client):
    for bad in ["..", "../../etc", "not-a-uuid"]:
        assert client.post("/api/extract-audio", json={"video_id": bad}).status_code == 400


def test_unknown_jobs_are_404(client):
    assert client.post("/api/extract-audio", json={"video_id": UNKNOWN}).status_code == 404


# ── step error mapping ───────────────────────────────────
def test_pipeline_errors_become_400_and_clear_outputs(client, make_job):
    video_id, job = make_job()  # no input.mp4, so extracting fails
    for stale in (p.AUDIO, p.TRANSCRIPT, p.OUTPUT):
        open(os.path.join(job, stale), "w").close()
    response = client.post("/api/extract-audio", json={"video_id": video_id})
    assert response.status_code == 400
    assert response.json()["detail"] == "Upload a video first."
    assert os.listdir(job) == []  # its own output and every later one are gone


def test_unexpected_errors_become_500(client, make_job, monkeypatch):
    video_id, job = make_job()
    open(os.path.join(job, p.VIDEO), "w").close()

    def broken(*cmd, cwd=None):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(p, "_run", broken)
    response = client.post("/api/extract-audio", json={"video_id": video_id})
    assert response.status_code == 500
    assert "disk on fire" in response.json()["detail"]


def test_request_bodies_are_validated(client, make_job):
    video_id, _ = make_job()
    bad = [
        ("/api/synthesize", {"video_id": video_id, "target_lang": "hi", "voice": "robot"}),
        ("/api/merge", {"video_id": video_id, "burn_subtitles": "maybe"}),
        ("/api/separate", {"video_id": video_id, "keep_background": "maybe"}),
        ("/api/translate", {"video_id": video_id}),
    ]
    for path, body in bad:
        assert client.post(path, json=body).status_code == 422, path


def test_unsupported_language_is_400(client, make_job):
    video_id, job = make_job()
    write_json(job, p.TRANSCRIPT, [{"start": 0, "end": 1, "text": "Hi."}])
    response = client.post("/api/translate", json={"video_id": video_id, "target_lang": "xx"})
    assert response.status_code == 400
    assert "Unsupported language" in response.json()["detail"]


def test_separate_is_skipped_unless_the_background_is_kept(client, make_job):
    video_id, _ = make_job()
    response = client.post("/api/separate", json={"video_id": video_id})
    assert response.json() == {"kept": False}


# ── editing the translation ──────────────────────────────
def test_editing_replaces_text_keeps_timing_and_clears_later_outputs(client, make_job):
    video_id, job = make_job()
    write_json(job, p.TRANSLATION, [{"start": 0, "end": 2, "text": "a"}, {"start": 2, "end": 4, "text": "b"}])
    for name in (p.SPEECH, p.SUBTITLES, p.OUTPUT):
        open(os.path.join(job, name), "w").close()

    response = client.put("/api/translation", json={"video_id": video_id, "texts": [" A ", "b"]})
    assert response.status_code == 200
    assert response.json()["sentences"] == [
        {"start": 0, "end": 2, "text": "A"},
        {"start": 2, "end": 4, "text": "b"},
    ]
    assert sorted(os.listdir(job)) == [p.TRANSLATION]


def test_editing_is_validated(client, make_job):
    video_id, job = make_job()
    write_json(job, p.TRANSLATION, [{"start": 0, "end": 2, "text": "a"}])
    put = lambda texts: client.put("/api/translation", json={"video_id": video_id, "texts": texts})  # noqa: E731
    assert put(["a", "b"]).status_code == 400   # wrong number of sentences
    assert put(["   "]).status_code == 400      # nothing left to say
    assert put(["x" * 2001]).status_code == 422  # too long


# ── downloads ────────────────────────────────────────────
def test_download_before_merge_is_404(client, make_job):
    video_id, _ = make_job()
    assert client.get(f"/api/download/{video_id}").status_code == 404


def test_download_filename_is_sanitised(client, make_job):
    video_id, job = make_job()
    open(os.path.join(job, p.OUTPUT), "wb").write(b"mp4")
    response = client.get(f"/api/download/{video_id}", params={"filename": '../evil"\r\nname'})
    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert 'filename="evil___name.mp4"' in disposition
    assert "\r" not in disposition and "/" not in disposition


def test_subtitles_download_formats(client, make_job):
    video_id, job = make_job()
    open(os.path.join(job, p.SUBTITLES), "wb").write(b"1\n")
    open(os.path.join(job, p.SUBTITLES_VTT), "wb").write(b"WEBVTT\n")
    srt = client.get(f"/api/subtitles/{video_id}", params={"filename": "talk.hi"})
    assert srt.status_code == 200 and 'filename="talk.hi.srt"' in srt.headers["content-disposition"]
    vtt = client.get(f"/api/subtitles/{video_id}", params={"format": "vtt"})
    assert vtt.headers["content-type"].startswith("text/vtt") and vtt.text == "WEBVTT\n"
    assert client.get(f"/api/subtitles/{video_id}", params={"format": "ass"}).status_code == 422
