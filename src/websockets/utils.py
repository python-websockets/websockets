import itertools


__all__ = ["apply_mask"]


def apply_mask(data: bytes, mask: bytes) -> bytes:
    """
    Apply masking to the data of a WebSocket message.

    ``data`` and ``mask`` are bytes-like objects.

    Return :class:`bytes`.

    """
    if len(mask) != 4:
        raise ValueError("mask must contain 4 bytes")

    return bytes(b ^ m for b, m in zip(data, itertools.cycle(mask)))
