"""Integration tests that run FFmpeg on generated media. A fake voice and a fake separator stand in
for the online speech service and the Demucs model, so these run offline in a few seconds."""
import json
import os
import subprocess
import wave
from types import SimpleNamespace

import numpy as np
import pytest
from conftest import ffmpeg, make_video, probe, write_json

import pipeline as p

pytestmark = pytest.mark.integration

SECONDS_PER_CHAR = 0.1


class FakeTTS:
    """Stands in for gTTS: writes a tone lasting 0.1 s per character of text."""
    calls = []

    def __init__(self, text, lang):
        self.text = text

    def save(self, path):
        FakeTTS.calls.append(self.text)
        duration = SECONDS_PER_CHAR * len(self.text)
        ffmpeg("-f", "lavfi", "-i", f"sine=frequency=300:duration={duration}", "-f", "mp3", path)


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "VOICES", {})  # no neural voice, so the (fake) gTTS path is used
    monkeypatch.setattr(p, "gTTS", FakeTTS)
    FakeTTS.calls = []
    make_video(tmp_path / p.VIDEO, seconds=6)
    p.extract_audio(str(tmp_path))
    return str(tmp_path)


def read_wav(path):
    with wave.open(path) as f:
        samples = np.frombuffer(f.readframes(f.getnframes()), dtype="<i2").astype(np.float32) / 32768
        return samples.reshape(-1, f.getnchannels()), f.getframerate()


def rms(samples):
    return float(np.sqrt(np.mean(samples ** 2)))


def srt_starts(job):
    text = open(os.path.join(job, p.SUBTITLES), encoding="utf-8").read()
    return [line.split(" --> ") for line in text.splitlines() if " --> " in line]


def seconds(stamp):
    h, m, s = stamp.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


# ── extract ──────────────────────────────────────────────
def test_extract_audio_writes_16k_mono(job):
    audio, rate = read_wav(os.path.join(job, p.AUDIO))
    assert rate == 16000 and audio.shape[1] == 1
    assert abs(len(audio) / rate - 6) < 0.1


def test_video_without_audio_is_rejected(tmp_path):
    make_video(tmp_path / p.VIDEO, seconds=2, audio=False)
    with pytest.raises(p.PipelineError, match="no audio track"):
        p.extract_audio(str(tmp_path))


# ── voice timing ─────────────────────────────────────────
def test_sentences_are_spoken_where_they_were_said(job):
    write_json(job, p.TRANSLATION, [
        {"start": 0.0, "end": 2.0, "text": "a" * 5},   # 0.5 s of speech, plenty of room
        {"start": 3.0, "end": 5.0, "text": "b" * 40},  # 4 s of speech, only 3 s left: sped up
    ])
    assert p.synthesize(job, "hi") == "Google TTS voice"

    total = p._duration(os.path.join(job, p.AUDIO))  # 6 s plus a few ms of encoder padding
    speech, rate = read_wav(os.path.join(job, p.SPEECH))
    assert abs(len(speech) / rate - total) < 0.01  # exactly as long as the original audio
    assert rms(speech[int(1.0 * rate):int(2.8 * rate)]) < 0.001  # the pause is kept
    assert rms(speech[int(3.2 * rate):int(5.8 * rate)]) > 0.01   # second sentence plays here

    (start1, end1), (start2, end2) = [map(seconds, cue) for cue in srt_starts(job)]
    assert start1 == 0 and 0.4 < end1 < 0.6
    assert start2 == 3.0 and end2 <= total + 0.001  # sped up to fit before the end


def test_unchanged_sentences_reuse_cached_clips(job):
    write_json(job, p.TRANSLATION, [
        {"start": 0, "end": 2, "text": "one"},
        {"start": 3, "end": 5, "text": "two"},
    ])
    p.synthesize(job, "hi")
    assert sorted(FakeTTS.calls) == ["one", "two"]

    FakeTTS.calls = []
    p.edit_translation(job, ["one", "three"])
    p.synthesize(job, "hi")
    assert FakeTTS.calls == ["three"]
    assert len(os.listdir(os.path.join(job, p.CLIPS))) == 2  # the clip for "two" was dropped


# ── merge ────────────────────────────────────────────────
def streams(path):
    return sorted(s["codec_type"] for s in json.loads(probe(path))["streams"])


def test_merge_burns_subtitles_into_the_picture(job):
    write_json(job, p.TRANSLATION, [{"start": 0, "end": 2, "text": "नमस्ते"}])
    p.synthesize(job, "hi")
    p.merge(job, burn_subtitles=True)
    output = os.path.join(job, p.OUTPUT)
    assert streams(output) == ["audio", "video"]
    assert abs(float(json.loads(probe(output))["format"]["duration"]) - 6) < 0.2


def test_merge_can_add_a_subtitle_track_instead(job):
    write_json(job, p.TRANSLATION, [{"start": 0, "end": 2, "text": "hello"}])
    p.synthesize(job, "hi")
    p.merge(job, burn_subtitles=False)
    output = os.path.join(job, p.OUTPUT)
    assert streams(output) == ["audio", "subtitle", "video"]
    assert abs(float(json.loads(probe(output))["format"]["duration"]) - 6) < 0.2  # not cut short


# ── background separation ────────────────────────────────
@pytest.fixture
def fake_separator(monkeypatch):
    """Pretend a quarter of the signal is speech, and use 2 s chunks so 6 s of audio has two joins."""
    monkeypatch.setattr(p, "_separator", SimpleNamespace(samplerate=44100))
    monkeypatch.setattr(p, "_isolate_vocals", lambda model, mix: mix * 0.25)
    monkeypatch.setattr(p, "SEPARATION_CHUNK_SECONDS", 2)


def test_separation_is_seamless_across_chunks(job, fake_separator):
    assert p.separate(job, keep_background=True) is True
    background, rate = read_wav(os.path.join(job, p.BACKGROUND))
    vocals, _ = read_wav(os.path.join(job, p.VOCALS))
    assert rate == 44100 and background.shape[1] == 2 and vocals.shape[1] == 1
    assert abs(len(background) / rate - 6) < 0.05 and len(vocals) == len(background)

    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", os.path.join(job, p.VIDEO),
         "-f", "f32le", "-ac", "2", "-ar", "44100", "-"],
        capture_output=True, check=True,
    ).stdout
    original = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)[:len(background)]
    error = rms(background[:len(original)] - original * 0.75)
    assert error < 0.02 * rms(original)  # the joins at 2 s and 4 s line up with the source


def test_new_voice_is_mixed_over_the_kept_background(job, fake_separator):
    p.separate(job, keep_background=True)
    write_json(job, p.TRANSLATION, [{"start": 4.0, "end": 5.0, "text": "hi"}])
    p.synthesize(job, "hi")
    speech, rate = read_wav(os.path.join(job, p.SPEECH))
    assert rate == 44100 and speech.shape[1] == 2
    assert rms(speech[: int(3.5 * rate)]) > 0.01  # background tone plays before the voice starts


def test_separation_is_skipped_by_default(job):
    assert p.separate(job) is False
    assert not os.path.exists(os.path.join(job, p.BACKGROUND))
