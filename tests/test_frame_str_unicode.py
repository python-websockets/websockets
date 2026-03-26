"""Tests for Frame.__str__() with incomplete UTF-8 sequences (issue #1695).

When DEBUG logging is enabled, websockets logs every frame with:
    logger.debug("> %s", frame)

This calls Frame.__str__(). For a non-final OP_TEXT frame that ends in the
middle of a multi-byte UTF-8 sequence, the original .decode() raised
UnicodeDecodeError and terminated the connection with code 1007 (INVALID_DATA).
"""

import pytest
from websockets.frames import Frame, OP_TEXT, OP_BINARY, OP_PING


# ── Multi-byte UTF-8 characters ───────────────────────────────────────────────

JAPANESE = "日本語テスト"   # each char = 3 bytes (0xe3…)
EMOJI    = "🦊🎉🐍"        # each char = 4 bytes


def _fragment(text: str, cut: int) -> bytes:
    """Return the first *cut* bytes of *text* encoded as UTF-8."""
    return text.encode("utf-8")[:cut]


@pytest.mark.parametrize("text,cut", [
    (JAPANESE * 100,  1001),   # cuts in the middle of a 3-byte kanji
    (JAPANESE * 100,  1002),   # cuts after 2 bytes of a 3-byte kanji
    (EMOJI * 100,      401),   # cuts in the middle of a 4-byte emoji
    (EMOJI * 100,      402),   # cuts after 2 bytes of a 4-byte emoji
    (EMOJI * 100,      403),   # cuts after 3 bytes of a 4-byte emoji
])
def test_str_non_final_text_frame_no_unicode_error(text, cut):
    """Frame.__str__() must not raise UnicodeDecodeError for partial UTF-8 frames."""
    data = _fragment(text, cut)
    assert data[-1:] not in (b"",)  # ensure the cut is non-trivial
    frame = Frame(opcode=OP_TEXT, data=data, fin=False)
    # Must not raise UnicodeDecodeError
    result = str(frame)
    assert "TEXT" in result
    # Replacement char U+FFFD should appear to signal the truncation
    assert "\ufffd" in result, (
        f"Expected replacement char in repr for partial UTF-8, got: {result!r:.80}"
    )


def test_str_complete_text_frame_no_replacement():
    """A complete (fin=True) UTF-8 frame must decode without replacement chars."""
    text = JAPANESE * 10
    frame = Frame(opcode=OP_TEXT, data=text.encode("utf-8"), fin=True)
    result = str(frame)
    assert "TEXT" in result
    assert "\ufffd" not in result


def test_str_ascii_text_frame():
    """Plain ASCII text must still work correctly."""
    frame = Frame(opcode=OP_TEXT, data=b"hello world", fin=True)
    result = str(frame)
    assert "'hello world'" in result


def test_str_binary_frame_unchanged():
    """Binary frames should not be affected by the fix."""
    frame = Frame(opcode=OP_BINARY, data=bytes(range(32)), fin=True)
    result = str(frame)
    assert "BINARY" in result


def test_str_ping_frame_unchanged():
    """Ping frames should not be affected by the fix."""
    frame = Frame(opcode=OP_PING, data=b"ping", fin=True)
    result = str(frame)
    assert "PING" in result
