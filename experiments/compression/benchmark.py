#!/usr/bin/env python

import collections
import pathlib
import sys
import time
import zlib


REPEAT = 10

WB, ML = 12, 5  # defaults used as a reference


def benchmark(data):
    size = collections.defaultdict(dict)
    duration = collections.defaultdict(dict)

    for wbits in range(9, 16):
        for memLevel in range(1, 10):
            encoder = zlib.compressobj(wbits=-wbits, memLevel=memLevel)
            encoded = []

            print(f"Compressing {REPEAT} times with {wbits=} and {memLevel=}")

            t0 = time.perf_counter()

            for _ in range(REPEAT):
                for item in data:
                    # Taken from PerMessageDeflate.encode
                    item = encoder.compress(item) + encoder.flush(zlib.Z_SYNC_FLUSH)
                    if item.endswith(b"\x00\x00\xff\xff"):
                        item = item[:-4]
                    encoded.append(item)

            t1 = time.perf_counter()

            size[wbits][memLevel] = sum(len(item) for item in encoded) / REPEAT
            duration[wbits][memLevel] = (t1 - t0) / REPEAT

    raw_size = sum(len(item) for item in data)

    print("=" * 79)
    print("Compression ratio")
    print("=" * 79)
    print("\t".join(["wb \\ ml"] + [str(memLevel) for memLevel in range(1, 10)]))
    for wbits in range(9, 16):
        print(
            "\t".join(
                [str(wbits)]
                + [
                    f"{100 * (1 - size[wbits][memLevel] / raw_size):.1f}%"
                    for memLevel in range(1, 10)
                ]
            )
        )
    print("=" * 79)
    print()

    print("=" * 79)
    print("CPU time")
    print("=" * 79)
    print("\t".join(["wb \\ ml"] + [str(memLevel) for memLevel in range(1, 10)]))
    for wbits in range(9, 16):
        print(
            "\t".join(
                [str(wbits)]
                + [
                    f"{1000 * duration[wbits][memLevel]:.1f}ms"
                    for memLevel in range(1, 10)
                ]
            )
        )
    print("=" * 79)
    print()

    print("=" * 79)
    print(f"Size vs. {WB} \\ {ML}")
    print("=" * 79)
    print("\t".join(["wb \\ ml"] + [str(memLevel) for memLevel in range(1, 10)]))
    for wbits in range(9, 16):
        print(
            "\t".join(
                [str(wbits)]
                + [
                    f"{100 * (size[wbits][memLevel] / size[WB][ML] - 1):.1f}%"
                    for memLevel in range(1, 10)
                ]
            )
        )
    print("=" * 79)
    print()

    print("=" * 79)
    print(f"Time vs. {WB} \\ {ML}")
    print("=" * 79)
    print("\t".join(["wb \\ ml"] + [str(memLevel) for memLevel in range(1, 10)]))
    for wbits in range(9, 16):
        print(
            "\t".join(
                [str(wbits)]
                + [
                    f"{100 * (duration[wbits][memLevel] / duration[WB][ML] - 1):.1f}%"
                    for memLevel in range(1, 10)
                ]
            )
        )
    print("=" * 79)
    print()


def main(corpus):
    data = [file.read_bytes() for file in corpus.iterdir()]
    benchmark(data)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} [directory]")
        sys.exit(2)
    main(pathlib.Path(sys.argv[1]))
