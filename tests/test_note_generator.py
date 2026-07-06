from tools.note_generator import pick_slide_for_chunk, split_transcript_into_chunks


def _seg(start, end, text="tekst"):
    return {"start": start, "end": end, "text": text}


def test_split_empty_transcript():
    assert split_transcript_into_chunks([]) == []


def test_split_single_chunk_keeps_all_segments():
    transcript = [_seg(0, 50, "a"), _seg(50, 120, "b")]
    chunks = split_transcript_into_chunks(transcript, chunk_duration=300)
    assert len(chunks) == 1
    assert chunks[0]["start"] == 0
    assert chunks[0]["end"] == 120
    assert chunks[0]["text"] == "a b"


def test_split_boundaries_do_not_leak_between_chunks():
    transcript = [_seg(0, 100, "a"), _seg(100, 250, "b"), _seg(250, 400, "c"), _seg(400, 450, "d")]
    chunks = split_transcript_into_chunks(transcript, chunk_duration=300)
    assert len(chunks) == 2
    # Pierwszy chunk konczy sie na koncu OSTATNIEGO segmentu w nim, nie nowego.
    assert chunks[0]["end"] == 250
    assert chunks[0]["text"] == "a b"
    assert chunks[1]["start"] == 250
    assert chunks[1]["end"] == 450
    assert chunks[1]["text"] == "c d"


def test_pick_slide_uses_chunk_midpoint():
    slides = [
        {"timestamp": 0, "file": "slides/s1.jpg"},
        {"timestamp": 120, "file": "slides/s2.jpg"},
        {"timestamp": 300, "file": "slides/s3.jpg"},
    ]
    # Srodek 200-400 to 300 -> slajd s3 (wyswietlany w polowie fragmentu).
    assert pick_slide_for_chunk(slides, 200, 400) == "slides/s3.jpg"
    # Srodek 0-100 to 50 -> nadal s1, mimo ze przed koncem chunku pojawil sie s2.
    assert pick_slide_for_chunk(slides, 0, 100) == "slides/s1.jpg"
    assert pick_slide_for_chunk([], 0, 100) is None
