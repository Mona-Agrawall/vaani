"""Unit tests for the text handling: sentence grouping, chunking, translation batching and subtitles."""
import pipeline as p


def segment(start, end, text):
    return {"start": start, "end": end, "text": text}


# ── sentence grouping ────────────────────────────────────
def test_segments_are_joined_until_a_sentence_ends():
    sentences = p._sentences([
        segment(0, 2, " So today we will talk"),
        segment(2, 4, "about Rome."),
        segment(4, 6, "It was big."),
    ])
    assert sentences == [
        segment(0, 4, "So today we will talk about Rome."),
        segment(4, 6, "It was big."),
    ]


def test_a_long_pause_starts_a_new_sentence():
    sentences = p._sentences([segment(0, 2, "first part"), segment(5, 6, "second part")])
    assert [s["text"] for s in sentences] == ["first part", "second part"]


def test_sentences_are_capped_in_length():
    segments = [segment(i, i + 1, f"word{i}") for i in range(30)]  # no punctuation at all
    sentences = p._sentences(segments)
    assert all(s["end"] - s["start"] <= p.MAX_SENTENCE_SECONDS for s in sentences)
    assert " ".join(s["text"] for s in sentences) == " ".join(f"word{i}" for i in range(30))


def test_empty_segments_are_ignored():
    assert p._sentences([segment(0, 1, "  "), segment(1, 2, "Hi.")]) == [segment(1, 2, "Hi.")]


# ── chunking for translation ─────────────────────────────
def test_chunks_respect_the_byte_limit_and_keep_all_text():
    text = "नमस्ते दुनिया। " * 40  # Devanagari is 3 bytes per character
    chunks = p._chunks(text.strip(), 100)
    assert all(p._size(c) <= 100 for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_a_word_longer_than_the_limit_is_cut_without_adding_spaces():
    chunks = p._chunks("x" * 50, 20)
    assert chunks == ["x" * 20, "x" * 20, "x" * 10]
    japanese = "私は財務管理を専攻しました" * 3  # no spaces, 3 bytes per character
    chunks = p._chunks(japanese, 30)
    assert all(p._size(c) <= 30 and " " not in c for c in chunks)
    assert "".join(chunks) == japanese


# ── translation batching ─────────────────────────────────
def test_lines_are_batched_into_few_requests():
    calls = []

    def service(text, lang):
        calls.append(text)
        return text.upper()

    lines = [f"line {i}" for i in range(10)]
    assert p._translate_lines_with(service, lines, "xx", 4500) == [line.upper() for line in lines]
    assert len(calls) == 1


def test_a_batch_whose_lines_get_merged_is_retried_line_by_line():
    def service(text, lang):
        return text.replace("\n", " ")  # a service that loses line breaks

    assert p._translate_lines_with(service, ["a", "b", "c"], "xx", 4500) == ["a", "b", "c"]


def test_an_oversized_line_is_translated_in_chunks():
    calls = []

    def service(text, lang):
        calls.append(text)
        return text

    long_line = "word. " * 50
    result = p._translate_lines_with(service, ["short", long_line.strip()], "xx", 60)
    assert result[0] == "short"
    assert result[1].split() == long_line.split()
    assert all(p._size(c) <= 60 for c in calls)


# ── subtitles ────────────────────────────────────────────
def lines_of(pieces):
    return [line for piece in pieces for line in piece.split("\n")]


def test_captions_have_at_most_two_lines_of_limited_width():
    pieces = p._caption_pieces("This sentence is short. " + "word " * 60)
    assert all(piece.count("\n") <= 1 for piece in pieces)
    assert all(p._width(line) <= p.CAPTION_LINE for line in lines_of(pieces))


def test_whole_sentences_stay_together_when_they_fit():
    text = "First sentence here. Second one is here too."  # 44 characters: one subtitle, two lines
    assert p._caption_pieces(text) == ["First sentence here. Second one is here\ntoo."]


def test_long_text_breaks_after_a_sentence_when_possible():
    first = "This first sentence is quite long and fills most of a subtitle."
    second = "The second one would not fit beside it."
    pieces = p._caption_pieces(f"{first} {second}")
    assert [piece.replace("\n", " ") for piece in pieces] == [first, second]


def test_japanese_wraps_by_display_width_without_adding_spaces():
    text = "こんにちは！私の名前はパトリシア・エスピリトゥです。フィリピン出身の二十四歳です。"
    pieces = p._caption_pieces(text)
    assert all(p._width(line) <= p.CAPTION_LINE for line in lines_of(pieces))
    assert "".join(lines_of(pieces)) == text


def test_caption_times_split_a_sentence_by_length():
    cues = p._captions([(10.0, 20.0, "a" * 40 + " " + "b" * 40 + " " + "c" * 40)])
    assert cues[0][0] == 10.0 and abs(cues[-1][1] - 20.0) < 1e-9
    assert all(a[1] == b[0] for a, b in zip(cues, cues[1:], strict=False))  # back to back, no gaps


def test_srt_and_vtt_formats():
    cues = [(1.5, 3.25, "Hello"), (3661.0, 3662.5, "two\nlines")]
    assert p._srt(cues) == (
        "1\n00:00:01,500 --> 00:00:03,250\nHello\n\n"
        "2\n01:01:01,000 --> 01:01:02,500\ntwo\nlines\n"
    )
    assert p._vtt(cues).startswith("WEBVTT\n\n1\n00:00:01.500 --> 00:00:03.250\nHello\n")


def test_ass_style_uses_the_scripts_own_font():
    assert "Style: Default,Noto Sans Tamil,18," in p._ass([], "ta")
    assert "Style: Default,Arial,18," in p._ass([], "fr")


def test_ass_events_escape_override_codes_and_break_lines():
    ass = p._ass([(0.0, 1.0, "a {\\b1}bold\\ word\nnext")])
    assert ass.endswith("Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,a b1bold word\\Nnext\n")
