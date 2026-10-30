import pytest

from jobpipe.text import normalize_text, split_text_into_chunks


def test_normalize_strips_urls_emojis_and_whitespace():
    raw = "Λογιστής 🚀  στην   Αθήνα\n\nΔείτε https://ex.gr/job?id=1 ή www.ex.gr ✅"
    assert normalize_text(raw, form="NFC") == "Λογιστής στην Αθήνα Δείτε ή"


@pytest.mark.parametrize("raw", [None, "", "   \n\t "])
def test_normalize_empty(raw):
    assert normalize_text(raw) == ""


def test_normalize_default_is_nfkd():
    # NFKD splits accented Greek letters into base letter + combining mark
    assert normalize_text("ά") == "ά"
    assert normalize_text("ά", form="NFC") == "ά"


def test_chunks_respect_word_limit():
    text = " ".join(f"w{i}" for i in range(10))
    chunks = split_text_into_chunks(text, max_words=4, max_chars=1000)
    assert [len(c.split()) for c in chunks] == [4, 4, 2]
    assert " ".join(chunks) == text


def test_chunks_respect_char_limit():
    text = "aaaa bbbb cccc dddd"
    chunks = split_text_into_chunks(text, max_words=100, max_chars=9)
    assert chunks == ["aaaa bbbb", "cccc dddd"]
    assert all(len(c) <= 9 for c in chunks)


def test_long_word_becomes_own_chunk_and_no_empty_chunks():
    text = "x" * 20 + " short"
    chunks = split_text_into_chunks(text, max_words=100, max_chars=10)
    assert chunks == ["x" * 20, "short"]
    assert "" not in chunks


def test_chunks_empty_text():
    assert split_text_into_chunks("", max_words=10, max_chars=100) == []
