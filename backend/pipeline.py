"""The video translation pipeline. Every step reads and writes files inside one job folder."""
import hashlib
import html
import json
import logging
import os
import re
import subprocess
import threading
import unicodedata
import wave
from concurrent.futures import ThreadPoolExecutor

import aiohttp
import edge_tts
import numpy as np
import requests
import torch
import whisper
from demucs.apply import apply_model
from demucs.pretrained import get_model
from gtts import gTTS, gTTSError
from gtts.lang import tts_langs

VIDEO = "input.mp4"
AUDIO = "audio.wav"
VOCALS = "vocals.wav"             # the original speech on its own, used for transcription
BACKGROUND = "background.wav"     # everything except the speech, mixed under the new voice
TRANSCRIPT = "transcript.json"    # timed sentences in the original language
TRANSLATION = "translation.json"  # the same sentences, translated
SPEECH = "speech.wav"
SUBTITLES = "subtitles.srt"       # for download and the optional subtitle track
SUBTITLES_VTT = "subtitles.vtt"   # the same cues for the browser preview
SUBTITLES_ASS = "subtitles.ass"   # styled copy used to burn subtitles into the picture
OUTPUT = "output.mp4"
CLIPS = "clips"                   # cache of spoken sentences, keyed by voice and text

# gTTS voices are a subset of Google Translate's languages, so this covers both steps
SUPPORTED_LANGUAGES = set(tts_langs())

# Microsoft neural voices (through edge-tts) as (female, male). Languages without an entry,
# or any run where this service fails, use gTTS instead.
VOICE_GENDERS = ("female", "male")
VOICES = {
    "hi": ("hi-IN-SwaraNeural", "hi-IN-MadhurNeural"),
    "bn": ("bn-IN-TanishaaNeural", "bn-IN-BashkarNeural"),
    "ta": ("ta-IN-PallaviNeural", "ta-IN-ValluvarNeural"),
    "te": ("te-IN-ShrutiNeural", "te-IN-MohanNeural"),
    "mr": ("mr-IN-AarohiNeural", "mr-IN-ManoharNeural"),
    "gu": ("gu-IN-DhwaniNeural", "gu-IN-NiranjanNeural"),
    "kn": ("kn-IN-SapnaNeural", "kn-IN-GaganNeural"),
    "ml": ("ml-IN-SobhanaNeural", "ml-IN-MidhunNeural"),
    "ur": ("ur-PK-UzmaNeural", "ur-PK-AsadNeural"),
    "es": ("es-ES-ElviraNeural", "es-ES-AlvaroNeural"),
    "fr": ("fr-FR-DeniseNeural", "fr-FR-HenriNeural"),
    "de": ("de-DE-KatjaNeural", "de-DE-ConradNeural"),
    "it": ("it-IT-ElsaNeural", "it-IT-DiegoNeural"),
    "pt": ("pt-BR-FranciscaNeural", "pt-BR-AntonioNeural"),
    "ru": ("ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural"),
    "ar": ("ar-SA-ZariyahNeural", "ar-SA-HamedNeural"),
    "ja": ("ja-JP-NanamiNeural", "ja-JP-KeitaNeural"),
    "ko": ("ko-KR-SunHiNeural", "ko-KR-InJoonNeural"),
}

# Google is tried first; MyMemory (free, no key) is the fallback when Google blocks or fails.
# Chunk limits are in UTF-8 bytes: Google allows ~5000 characters, MyMemory 500 bytes per request.
GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"
GOOGLE_CHUNK_BYTES = 4500
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
MYMEMORY_CHUNK_BYTES = 450

SEPARATION_MODEL = "htdemucs"     # Demucs model that splits speech from music and ambience
SEPARATION_CHUNK_SECONDS = 30     # audio is separated in chunks so memory stays flat on long videos
SEPARATION_FADE_SECONDS = 1       # neighbouring chunks overlap by this much and are crossfaded

MAX_SENTENCE_SECONDS = 15  # Whisper segments are joined into sentences up to this long
SENTENCE_GAP_SECONDS = 1.5  # a pause this long always starts a new sentence
SAMPLE_RATE = 24000         # dubbed track: 16-bit mono PCM
BYTES_PER_SECOND = SAMPLE_RATE * 2
MAX_TEMPO = 2.0             # the most a sentence is sped up to fit before the next one starts
TTS_WORKERS = 4
CAPTION_LINE = 42           # subtitle line width; each subtitle has at most two lines

# Font for burned-in subtitles. Naming the script's own font matters: when libass has to fall back
# character by character it can mix fonts within a word (e.g. Tamil letters from Noto Sans Grantha),
# which breaks the shaping. These are the Noto fonts the Docker image installs; where one is missing
# (e.g. on Windows) libass falls back to a system font that covers the script.
DEFAULT_SUBTITLE_FONT = "Arial"
SUBTITLE_FONTS = {
    "hi": "Noto Sans Devanagari",
    "mr": "Noto Sans Devanagari",
    "bn": "Noto Sans Bengali",
    "ta": "Noto Sans Tamil",
    "te": "Noto Sans Telugu",
    "gu": "Noto Sans Gujarati",
    "kn": "Noto Sans Kannada",
    "ml": "Noto Sans Malayalam",
    "ur": "Noto Naskh Arabic",
    "ar": "Noto Naskh Arabic",
    "ja": "Noto Sans CJK JP",
    "ko": "Noto Sans CJK KR",
}

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 384
PlayResY: 288
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},18,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,1.3,0,2,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""  # noqa: E501 (the ASS format lines cannot be wrapped)

log = logging.getLogger(__name__)
# Both models are loaded on first use and kept; each lock lets one job use its model at a time
_model = None
_model_lock = threading.Lock()
_separator = None
_separator_lock = threading.Lock()


class PipelineError(Exception):
    """A step failed for a reason worth showing to the user."""


# ── helpers ──────────────────────────────────────────────
def _run(*cmd, cwd=None):
    result = subprocess.run(cmd, capture_output=True, cwd=cwd)
    if result.returncode != 0:
        lines = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise PipelineError(f"{cmd[0]} failed: {lines[-1] if lines else 'unknown error'}")
    return result.stdout


def _duration(path):
    output = _run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path)
    return float(output.decode())


def _require(job, name, missing_message):
    path = os.path.join(job, name)
    if not os.path.exists(path):
        raise PipelineError(missing_message)
    return path


def _load(job, name, missing_message):
    with open(_require(job, name, missing_message), encoding="utf-8") as f:
        return json.load(f)


def _save(job, name, data):
    with open(os.path.join(job, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _write(job, name, text):
    with open(os.path.join(job, name), "w", encoding="utf-8") as f:
        f.write(text)


def _check_language(lang):
    if lang not in SUPPORTED_LANGUAGES:
        raise PipelineError(f"Unsupported language: {lang}")


def _size(text):
    return len(text.encode("utf-8"))


# ── separation ───────────────────────────────────────────
def _read_stereo(video, start, length, rate):
    """Decode `length` seconds of the video's audio from `start` as a (2, samples) tensor."""
    raw = _run("ffmpeg", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", video,
               "-vn", "-f", "f32le", "-ac", "2", "-ar", str(rate), "-")
    return torch.from_numpy(np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.copy())


def _pcm16(signal):
    """A (channels, samples) float tensor as interleaved 16-bit PCM."""
    return (signal.clamp(-1, 1).T.numpy() * 32767).astype("<i2").tobytes()


def _isolate_vocals(model, mix):
    """Run Demucs on one chunk and return its vocals, shaped like `mix`."""
    reference = mix.mean(0)
    mean, std = reference.mean(), reference.std() + 1e-8  # Demucs expects normalised input
    with torch.no_grad():
        sources = apply_model(model, ((mix - mean) / std)[None], device="cpu", progress=False)[0]
    return sources[model.sources.index("vocals")] * std + mean


# ── transcription ────────────────────────────────────────
def _sentences(segments):
    """Join Whisper's segments (often half sentences) into whole sentences, so each one
    translates with its full context and is spoken as one unit."""
    sentences, current = [], None
    for segment in segments:
        text = segment["text"].strip()
        if not text:
            continue
        if current and (segment["start"] - current["end"] > SENTENCE_GAP_SECONDS
                        or segment["end"] - current["start"] > MAX_SENTENCE_SECONDS):
            sentences.append(current)
            current = None
        if current:
            current["end"] = segment["end"]
            current["text"] += " " + text
        else:
            current = {"start": segment["start"], "end": segment["end"], "text": text}
        if re.search(r"[.!?。！？।]$", text):
            sentences.append(current)
            current = None
    return sentences + [current] if current else sentences


# ── translation ──────────────────────────────────────────
def _chunks(text, limit):
    """Split text into pieces under `limit` UTF-8 bytes, preferring sentence boundaries."""
    units = []
    for sentence in re.split(r"(?<=[.!?。！？।])\s+", text):
        if _size(sentence) <= limit:
            units.append(sentence)
            continue
        for word in sentence.split():
            # a word longer than the limit is cut into pieces that each nearly fill a chunk,
            # so the packing below never glues two of them back together with a space
            piece = ""
            for char in word:
                if piece and _size(piece + char) > limit:
                    units.append(piece)
                    piece = char
                else:
                    piece += char
            units.append(piece)

    chunks, current = [], ""
    for unit in units:
        if current and _size(current) + 1 + _size(unit) > limit:
            chunks.append(current)
            current = unit
        else:
            current = f"{current} {unit}" if current else unit
    return chunks + [current] if current else chunks


def _google(text, lang):
    response = requests.post(
        GOOGLE_URL,
        params={"client": "gtx", "sl": "auto", "tl": lang, "dt": "t"},
        data={"q": text},
        timeout=30,
    )
    response.raise_for_status()
    return "".join(segment[0] for segment in response.json()[0] if segment[0])


def _mymemory(text, lang):
    response = requests.get(MYMEMORY_URL, params={"q": text, "langpair": f"autodetect|{lang}"}, timeout=30)
    response.raise_for_status()
    data = response.json()
    if data.get("quotaFinished") or str(data.get("responseStatus")) != "200":
        raise requests.RequestException(data.get("responseDetails") or "MyMemory quota reached")
    return html.unescape(data["responseData"]["translatedText"])


def _translate_lines_with(service, lines, lang, limit):
    """Translate many lines in as few requests as possible. Both services keep line breaks,
    so a batch is sent as one newline-separated text and split back afterwards."""
    batches, batch = [], []
    for line in lines:
        if batch and _size("\n".join(batch + [line])) > limit:
            batches.append(batch)
            batch = []
        batch.append(line)
    if batch:
        batches.append(batch)

    translated = []
    for batch in batches:
        text = "\n".join(batch)
        result = service(text, lang).split("\n") if _size(text) <= limit else []
        if len(result) != len(batch):  # an oversized line, or the service merged lines: go one by one
            result = [" ".join(service(chunk, lang) for chunk in _chunks(line, limit)) for line in batch]
        translated += [line.strip() for line in result]
    return translated


def _translate_lines(lines, lang):
    try:
        return _translate_lines_with(_google, lines, lang, GOOGLE_CHUNK_BYTES)
    except (requests.RequestException, ValueError, IndexError, TypeError) as error:
        log.warning("Google Translate failed (%s), falling back to MyMemory", error)
    try:
        return _translate_lines_with(_mymemory, lines, lang, MYMEMORY_CHUNK_BYTES)
    except (requests.RequestException, ValueError, KeyError) as error:
        raise PipelineError(
            f"Translation services are unavailable right now ({error}). Try again in a few minutes."
        ) from error


# ── speech ───────────────────────────────────────────────
def _speak_all(texts, lang, gender, job):
    """Get one MP3 per text, a few at a time. Returns the paths and a description of the voice
    used. Every clip comes from the same service, so one video never mixes voices. Clips are
    cached by voice and text, so after an edit only the changed sentences are generated again."""
    folder = os.path.join(job, CLIPS)
    os.makedirs(folder, exist_ok=True)

    def speak_with(engine, speak):
        def one(text):
            path = os.path.join(folder, hashlib.sha1(f"{engine}\n{text}".encode()).hexdigest() + ".mp3")
            if not os.path.exists(path):
                # written under a temporary name, so the cache never holds half a clip
                speak(text, path + ".part")
                os.replace(path + ".part", path)
            return path

        distinct = list(dict.fromkeys(texts))
        with ThreadPoolExecutor(TTS_WORKERS) as pool:
            unique = dict(zip(distinct, pool.map(one, distinct), strict=True))
        used = {os.path.basename(path) for path in unique.values()}
        for entry in os.scandir(folder):  # drop clips that no sentence uses any more
            if entry.name not in used:
                os.remove(entry.path)
        return [unique[text] for text in texts]

    voice = VOICES.get(lang, (None, None))[VOICE_GENDERS.index(gender)]
    if voice:
        try:
            paths = speak_with(voice, lambda text, path: edge_tts.Communicate(text, voice).save_sync(path))
            name = voice.split("-")[2].removesuffix("Neural")
            return paths, f"{name}, Microsoft neural voice"
        except (edge_tts.exceptions.EdgeTTSException, aiohttp.ClientError, OSError) as error:
            log.warning("edge-tts failed (%s), falling back to gTTS", error)
    try:
        paths = speak_with(f"gtts-{lang}", lambda text, path: gTTS(text=text, lang=lang).save(path))
        return paths, "Google TTS voice"
    except gTTSError as error:
        raise PipelineError(f"Text-to-speech failed: {error}") from error


def _pcm(path, tempo=1.0):
    """Decode a clip to raw PCM with the silence at both ends trimmed, optionally sped up."""
    trim = "silenceremove=start_periods=1:start_threshold=-50dB"
    return _run("ffmpeg", "-loglevel", "error", "-i", path,
                "-af", f"{trim},areverse,{trim},areverse,atempo={tempo:.4f}",
                "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-")


# ── subtitles ────────────────────────────────────────────
def _width(text):
    """Display width: CJK characters take two columns."""
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)


def _tokens(text, limit):
    """Words, each keeping its trailing space. Words wider than `limit` (Japanese has
    no spaces, so a whole sentence is one "word") are cut into parts."""
    tokens = []
    for word in re.findall(r"\S+\s*", text):
        part = ""
        for char in word:
            if part and _width((part + char).rstrip()) > limit:
                tokens.append(part)
                part = char
            else:
                part += char
        tokens.append(part)
    return tokens


def _pack(tokens, limit):
    """Join tokens greedily into strings no wider than `limit`."""
    packed, current = [], ""
    for token in tokens:
        if current and _width((current + token).rstrip()) > limit:
            packed.append(current.rstrip())
            current = token
        else:
            current += token
    return packed + [current.rstrip()] if current.strip() else packed


def _caption_pieces(text):
    """Split text into subtitles of at most two lines, keeping whole sentences
    together where they fit."""
    units = []
    for sentence in filter(None, re.split(r"(?<=[.!?।]\s)|(?<=[。！？])", text)):
        fits = _width(sentence.rstrip()) <= 2 * CAPTION_LINE
        units += [sentence] if fits else _tokens(sentence, CAPTION_LINE)
    pieces = []
    for piece in _pack(units, 2 * CAPTION_LINE):
        lines = _pack(_tokens(piece, CAPTION_LINE), CAPTION_LINE)
        pieces += ["\n".join(lines[i:i + 2]) for i in range(0, len(lines), 2)]
    return pieces


def _captions(spoken):
    """Turn (start, end, sentence) into subtitle cues, sharing each sentence's time
    between its pieces by length so long sentences don't fill the screen."""
    cues = []
    for start, end, text in spoken:
        pieces = _caption_pieces(text)
        per_char = (end - start) / sum(map(len, pieces))
        for piece in pieces:
            piece_end = start + per_char * len(piece)
            cues.append((start, piece_end, piece))
            start = piece_end
    return cues


def _srt(cues, separator=","):
    def stamp(seconds):
        ms = round(seconds * 1000)
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}{separator}{ms % 1000:03}"
    return "\n".join(f"{i}\n{stamp(start)} --> {stamp(end)}\n{text}\n"
                     for i, (start, end, text) in enumerate(cues, 1))


def _vtt(cues):
    return "WEBVTT\n\n" + _srt(cues, separator=".")


def _ass_text(text):
    # braces and backslashes are ASS override codes; \N is a line break
    return re.sub(r"[{}\\]", "", text).replace("\n", r"\N")


def _ass(cues, lang=None):
    def stamp(seconds):
        cs = round(seconds * 100)
        return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"
    events = (f"Dialogue: 0,{stamp(start)},{stamp(end)},Default,,0,0,0,,{_ass_text(text)}"
              for start, end, text in cues)
    header = ASS_HEADER.replace("{font}", SUBTITLE_FONTS.get(lang, DEFAULT_SUBTITLE_FONT))
    return header + "\n".join(events) + "\n"


# ── steps ────────────────────────────────────────────────
def extract_audio(job):
    video = _require(job, VIDEO, "Upload a video first.")
    has_audio = _run("ffprobe", "-v", "error", "-select_streams", "a",
                     "-show_entries", "stream=index", "-of", "csv=p=0", video).strip()
    if not has_audio:
        raise PipelineError("This video has no audio track.")
    _run("ffmpeg", "-y", "-loglevel", "error", "-i", video,
         "-vn", "-ac", "1", "-ar", "16000", os.path.join(job, AUDIO))


def separate(job, keep_background=False):
    """Split the original audio into speech and background (music, ambience) with Demucs.
    Runs only when the background is kept. Returns whether it ran."""
    global _separator
    if not keep_background:
        return False
    video = _require(job, VIDEO, "Upload a video first.")
    total = _duration(_require(job, AUDIO, "Extract the audio first."))

    with _separator_lock:
        if _separator is None:
            _separator = get_model(SEPARATION_MODEL).eval()
        rate = _separator.samplerate
        fade = SEPARATION_FADE_SECONDS * rate
        with wave.open(os.path.join(job, VOCALS), "wb") as vocals_out, \
             wave.open(os.path.join(job, BACKGROUND), "wb") as background_out:
            for out, channels in ((vocals_out, 1), (background_out, 2)):
                out.setnchannels(channels)
                out.setsampwidth(2)
                out.setframerate(rate)

            # Chunk k covers [k*C - F, (k+1)*C): its first F seconds repeat the end of the previous
            # chunk and are crossfaded with it, so the joins are inaudible.
            held, start = None, 0.0
            while start < total:
                lead = SEPARATION_FADE_SECONDS if start else 0
                mix = _read_stereo(video, start - lead, SEPARATION_CHUNK_SECONDS + lead, rate)
                if mix.shape[1] <= fade:  # nothing new left (durations differ by a few ms)
                    break
                vocals = _isolate_vocals(_separator, mix)
                background = mix - vocals
                if held is not None:
                    n = min(fade, held[0].shape[1], vocals.shape[1])
                    ramp = torch.linspace(0, 1, n)
                    vocals[:, :n] = held[0][:, :n] * (1 - ramp) + vocals[:, :n] * ramp
                    background[:, :n] = held[1][:, :n] * (1 - ramp) + background[:, :n] * ramp
                start += SEPARATION_CHUNK_SECONDS
                end = vocals.shape[1] - fade if start < total else vocals.shape[1]
                vocals_out.writeframes(_pcm16(vocals[:, :end].mean(0, keepdim=True)))
                background_out.writeframes(_pcm16(background[:, :end]))
                held = (vocals[:, end:], background[:, end:])
    return True


def transcribe(job):
    global _model
    # Whisper is more accurate on the isolated speech when the background was separated
    vocals = os.path.join(job, VOCALS)
    audio = vocals if os.path.exists(vocals) else _require(job, AUDIO, "Extract the audio first.")
    with _model_lock:  # load Whisper once and run one transcription at a time
        if _model is None:
            _model = whisper.load_model("base")
        segments = _model.transcribe(audio, fp16=False)["segments"]
    sentences = _sentences(segments)
    if not sentences:
        raise PipelineError("No speech was detected in this video.")
    _save(job, TRANSCRIPT, sentences)
    return sentences


def translate(job, lang):
    """Translate every sentence. The result lines up one to one with the transcript."""
    _check_language(lang)
    sentences = _load(job, TRANSCRIPT, "Generate the transcript first.")
    translated = _translate_lines([s["text"] for s in sentences], lang)
    if not any(translated):
        raise PipelineError("Translation came back empty.")
    sentences = [{**s, "text": text} for s, text in zip(sentences, translated, strict=True)]
    _save(job, TRANSLATION, sentences)
    return sentences


def edit_translation(job, texts):
    """Replace the translated text of each sentence, keeping its timing. The voice, subtitles
    and video made from the old text are deleted, so they have to be generated again."""
    sentences = _load(job, TRANSLATION, "Translate the transcript first.")
    if len(texts) != len(sentences):
        raise PipelineError(f"Expected {len(sentences)} sentences, got {len(texts)}.")
    if not any(text.strip() for text in texts):
        raise PipelineError("The translation can't be empty.")
    clear_outputs(job, synthesize)
    sentences = [{**s, "text": text.strip()} for s, text in zip(sentences, texts, strict=True)]
    _save(job, TRANSLATION, sentences)
    return sentences


def synthesize(job, lang, gender="female"):
    """Speak each translated sentence at the moment it was said in the original
    (sped up if it would run into the next one), then write matching subtitles.
    Returns a description of the voice used."""
    _check_language(lang)
    sentences = [s for s in _load(job, TRANSLATION, "Translate the transcript first.")
                 if re.search(r"\w", s["text"])]
    if not sentences:
        raise PipelineError("The translation has no text that can be spoken.")
    total = _duration(_require(job, AUDIO, "Extract the audio first."))
    if total <= 0:
        raise PipelineError("The original audio track is empty.")

    track = bytearray(int(total * SAMPLE_RATE) * 2)
    spoken, cursor = [], 0.0
    clips, voice = _speak_all([s["text"] for s in sentences], lang, gender, job)
    for i, (sentence, clip) in enumerate(zip(sentences, clips, strict=True)):
        start = max(sentence["start"], cursor)
        if start >= total:
            break
        room = (sentences[i + 1]["start"] if i + 1 < len(sentences) else total) - start
        pcm = _pcm(clip)
        length = len(pcm) / BYTES_PER_SECOND
        if length > room:
            pcm = _pcm(clip, min(length / room, MAX_TEMPO) if room > 0 else MAX_TEMPO)
            length = len(pcm) / BYTES_PER_SECOND
        offset = int(start * SAMPLE_RATE) * 2
        pcm = pcm[:len(track) - offset]
        track[offset:offset + len(pcm)] = pcm
        cursor = start + length
        spoken.append((start, min(cursor, total), sentence["text"]))

    speech = os.path.join(job, SPEECH)
    with wave.open(speech, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(track)
    background = os.path.join(job, BACKGROUND)
    if os.path.exists(background):  # lay the new voice over the original music and ambience
        mixed = os.path.join(job, "mixed.wav")
        _run("ffmpeg", "-y", "-loglevel", "error", "-i", speech, "-i", background,
             "-filter_complex", "amix=inputs=2:duration=first:normalize=0", "-ac", "2", "-ar", "44100", mixed)
        os.replace(mixed, speech)

    cues = _captions(spoken)
    _write(job, SUBTITLES, _srt(cues))
    _write(job, SUBTITLES_VTT, _vtt(cues))
    _write(job, SUBTITLES_ASS, _ass(cues, lang))
    return voice


def merge(job, burn_subtitles=True):
    """Swap in the dubbed audio. Subtitles are either drawn into the picture (needs a
    re-encode) or added as a track viewers can switch on in their player."""
    video = _require(job, VIDEO, "Upload a video first.")
    speech = _require(job, SPEECH, "Generate the translated audio first.")
    subtitles = _require(job, SUBTITLES, "Generate the subtitles first.")
    output = os.path.join(job, OUTPUT)
    if burn_subtitles:
        _require(job, SUBTITLES_ASS, "Generate the subtitles first.")
        # runs inside the job folder so the filter gets a plain file name (no path escaping);
        # complex shaping is needed for scripts like Tamil and Bengali to render correctly
        _run("ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", speech,
             "-map", "0:v:0", "-map", "1:a:0", "-vf", f"ass={SUBTITLES_ASS}:shaping=complex",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", output, cwd=job)
    else:
        # no -shortest here: it would cut the video where the last subtitle ends
        _run("ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", speech, "-i", subtitles,
             "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0",
             "-c:v", "copy", "-c:a", "aac", "-c:s", "mov_text", output)


# Outputs of each step, in pipeline order
STEP_OUTPUTS = {
    extract_audio: (AUDIO,),
    separate: (VOCALS, BACKGROUND),
    transcribe: (TRANSCRIPT,),
    translate: (TRANSLATION,),
    synthesize: (SPEECH, SUBTITLES, SUBTITLES_VTT, SUBTITLES_ASS),
    merge: (OUTPUT,),
}


def clear_outputs(job, step):
    """Delete the outputs of `step` and of every later step, so nothing stale is ever reused."""
    steps = list(STEP_OUTPUTS)
    for later in steps[steps.index(step):]:
        for name in STEP_OUTPUTS[later]:
            path = os.path.join(job, name)
            if os.path.exists(path):
                os.remove(path)
