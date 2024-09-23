#!/usr/bin/env python

"""
Profile the permessage-deflate extension.

Usage::
    $ pip install line_profiler
    $ python experiments/compression/corpus.py experiments/compression/corpus
    $ PYTHONPATH=src python -m kernprof \
        --line-by-line \
        --prof-mod src/websockets/extensions/permessage_deflate.py \
        --view \
        experiments/profiling/compression.py experiments/compression/corpus 12 5 6

"""

import pathlib
import sys

from websockets.extensions.permessage_deflate import PerMessageDeflate
from websockets.frames import OP_TEXT, Frame


def compress_and_decompress(corpus, max_window_bits, memory_level, level):
    extension = PerMessageDeflate(
        remote_no_context_takeover=False,
        local_no_context_takeover=False,
        remote_max_window_bits=max_window_bits,
        local_max_window_bits=max_window_bits,
        compress_settings={"memLevel": memory_level, "level": level},
    )
    for data in corpus:
        frame = Frame(OP_TEXT, data)
        frame = extension.encode(frame)
        frame = extension.decode(frame)


if __name__ == "__main__":
    if len(sys.argv) < 2 or not pathlib.Path(sys.argv[1]).is_dir():
        print(f"Usage: {sys.argv[0]} <directory> [<max_window_bits>] [<mem_level>]")
    corpus = [file.read_bytes() for file in pathlib.Path(sys.argv[1]).iterdir()]
    max_window_bits = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    memory_level = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    level = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    compress_and_decompress(corpus, max_window_bits, memory_level, level)
