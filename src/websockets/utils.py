import itertools
import logging

try:
    import contextvars

    logging_contextvar = contextvars.ContextVar(
        "websockets_logging_context", default=None
    )
except ImportError:
    logging_contextvar = None

__all__ = ["apply_mask"]


def apply_mask(data: bytes, mask: bytes) -> bytes:
    """
    Apply masking to the data of a WebSocket message.

    :param data: Data to mask
    :param mask: 4-bytes mask

    """
    if len(mask) != 4:
        raise ValueError("mask must contain 4 bytes")

    return bytes(b ^ m for b, m in zip(data, itertools.cycle(mask)))


class ContextLoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger, extra={}):
        super().__init__(logger, extra)

    def process(self, msg, kwargs):
        context = logging_contextvar.get() if logging_contextvar else None
        formatted_msg = f"[{context}] {msg}" if context else msg
        return formatted_msg, kwargs


def set_logging_contextvar(value):
    if logging_contextvar:
        logging_contextvar.set(value)
    else:
        raise ModuleNotFoundError("contextvars module not present")
