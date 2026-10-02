#!/usr/bin/env python3
"""Hardware smoke for CMD_IMPORT_SYSMEM_FD (server 1.2): one host buffer DMA-mapped for two cards.

Run on a Mac with two cards behind this fork's TinyGPU, with nothing else
connected to their servers (each server takes one client - stop any engine
serving on the cards first):

    python3 tests/import_sysmem_smoke.py --cards 0,1

It talks the server protocol directly (33-byte requests, 17-byte responses):

1. PING both servers: each must report 1.2 or later.
2. MAP_SYSMEM_FD a 2 MiB region on the first card, keep its fd, and mark the
   region past the address table the server writes at its head.
3. IMPORT_SYSMEM_FD that fd on the second card: a non-empty (iova, length)
   table covering the region, and the region's bytes unchanged.
4. RESET on the second card is refused while the imported mapping is live.
5. Size boundaries: an import of exactly 16 KiB succeeds; no fd, 4 KiB,
   a non-4-KiB-multiple size, and one past the region's size are refused.
6. An 8 MiB region imports in at most 32 segments that cover it.

With --allow-reset it also proves the mapping is released on disconnect: it
reconnects and expects a RESET to succeed. That resets the second card - run
it only when the card may be reset (a hot reset on Blackwell, FLR otherwise).

Prints `import ok` and exits 0, or names the first failed check and exits 1.
"""
from __future__ import annotations

import argparse
import mmap
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time

CMD_MAP_SYSMEM_FD, CMD_RESET, CMD_PING, CMD_IMPORT_SYSMEM_FD = 2, 5, 12, 13
SERVER_1_2 = 0x00010200
REGION_BYTES = 2 << 20
BIG_REGION_BYTES = 8 << 20
MAX_SEGMENTS = 32
MARKER = b"legwork-card-bridge-import-smoke"
MARKER_OFFSET = 64 << 10  # past the address table MAP_SYSMEM_FD writes at the head
APP = "/Applications/TinyGPU.app/Contents/MacOS/TinyGPU"


class SmokeFailed(Exception):
    pass


def socket_path(index: int) -> str:
    # tinygrad's card 0 socket, and the multi-card build's one per card (the Legwork launcher's names).
    name = "tinygpu.sock" if index == 0 else "tinygpu-%d.sock" % index
    return os.path.join(tempfile.gettempdir(), name)


def connect(index: int, app: str) -> socket.socket:
    path = socket_path(index)
    for attempt in range(100):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(path)
            return sock
        except (ConnectionRefusedError, FileNotFoundError):
            sock.close()
            if attempt == 0:
                try:
                    subprocess.Popen([app, "server", path, "--device", str(index)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except OSError as exc:
                    raise SmokeFailed("could not start the TinyGPU server for card %d from %s: %s" % (index, app, exc))
            time.sleep(0.05)
    raise SmokeFailed("could not reach the TinyGPU server for card %d at %s" % (index, path))


def request(cmd: int, arg0: int = 0, arg1: int = 0, arg2: int = 0) -> bytes:
    return struct.pack("<BIIQQQ", cmd, 0, 0, arg0, arg1, arg2)


def recv_exact(sock: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise SmokeFailed("the server closed the connection")
        data += chunk
    return data


def response(sock: socket.socket) -> tuple[int, int, int]:
    status, resp0, resp1 = struct.unpack("<BQQ", recv_exact(sock, 17))
    return status, resp0, resp1


def error_text(sock: socket.socket, length: int) -> str:
    return recv_exact(sock, length).decode("utf-8", "replace") if length else ""


def ping(sock: socket.socket) -> int:
    sock.sendall(request(CMD_PING))
    status, version, _dext = response(sock)
    return version if status == 0 else 0


def map_sysmem_fd(sock: socket.socket, size: int) -> tuple[int, mmap.mmap]:
    sock.sendall(request(CMD_MAP_SYSMEM_FD, size, 0))
    msg, anc, _flags, _addr = sock.recvmsg(17, socket.CMSG_LEN(4))
    status, mapped, _idx = struct.unpack("<BQQ", msg)
    if status != 0 or not anc:
        raise SmokeFailed("MAP_SYSMEM_FD was refused: %s" % error_text(sock, mapped))
    fd = struct.unpack("<i", anc[0][2][:4])[0]
    return fd, mmap.mmap(fd, mapped, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)


def import_fd(sock: socket.socket, fd: int | None, size: int) -> tuple[int, list[tuple[int, int]], str]:
    # (status, segments, error text). fd None sends the trailing byte without SCM_RIGHTS.
    sock.sendall(request(CMD_IMPORT_SYSMEM_FD, size))
    ancillary = [] if fd is None else [(socket.SOL_SOCKET, socket.SCM_RIGHTS, struct.pack("<i", fd))]
    sock.sendmsg([b"\0"], ancillary)
    status, resp0, resp1 = response(sock)
    if status != 0:
        return status, [], error_text(sock, resp0)
    raw = recv_exact(sock, resp1 * 16)
    return status, [struct.unpack_from("<QQ", raw, 16 * i) for i in range(resp1)], ""


def check(condition: bool, what: str) -> None:
    if not condition:
        raise SmokeFailed(what)


def run(cards: tuple[int, int], app: str, allow_reset: bool) -> None:
    owner, importer = cards
    a, b = connect(owner, app), connect(importer, app)
    for index, sock in ((owner, a), (importer, b)):
        version = ping(sock)
        check(version >= SERVER_1_2, "card %d's server reports %#x; the import needs server 1.2 (0x00010200)" % (index, version))

    fd, region = map_sysmem_fd(a, REGION_BYTES)
    region[MARKER_OFFSET:MARKER_OFFSET + len(MARKER)] = MARKER
    before = bytes(region[:MARKER_OFFSET + len(MARKER)])
    status, segments, error = import_fd(b, fd, REGION_BYTES)
    check(status == 0, "the import was refused: %s" % error)
    check(len(segments) >= 1 and all(length > 0 for _iova, length in segments), "the import returned an empty address table")
    check(sum(length for _iova, length in segments) >= REGION_BYTES, "the address table covers less than the region")
    check(bytes(region[:MARKER_OFFSET + len(MARKER)]) == before, "the import wrote into the region")

    b.sendall(request(CMD_RESET))
    status, length, _flags = response(b)
    check(status != 0 and "mappings are live" in error_text(b, length), "a reset was not refused while the imported mapping is live")

    status, _segments, error = import_fd(b, None, REGION_BYTES)
    check(status != 0 and "no file descriptor" in error, "an import without an fd was not refused")
    status, _segments, error = import_fd(b, fd, 4 << 10)
    check(status != 0 and "4 KiB multiple" in error, "a 4 KiB import was not refused")
    status, _segments, error = import_fd(b, fd, (16 << 10) + 4)
    check(status != 0 and "4 KiB multiple" in error, "a non-4-KiB-multiple import was not refused")
    status, _segments, error = import_fd(b, fd, REGION_BYTES * 2)
    check(status != 0 and "smaller than the requested size" in error, "an import past the region's size was not refused")
    status, segments, error = import_fd(b, fd, 16 << 10)
    check(status == 0, "the 16 KiB minimum import was refused: %s" % error)
    check(sum(length for _iova, length in segments) >= 16 << 10, "the 16 KiB import's address table covers less than the size")

    big_fd, _big = map_sysmem_fd(a, BIG_REGION_BYTES)
    status, segments, error = import_fd(b, big_fd, BIG_REGION_BYTES)
    check(status == 0, "the 8 MiB import was refused: %s" % error)
    check(len(segments) <= MAX_SEGMENTS, "the 8 MiB region came back in %d segments (at most %d)" % (len(segments), MAX_SEGMENTS))
    check(sum(length for _iova, length in segments) >= BIG_REGION_BYTES, "the 8 MiB region's address table covers less than the region")

    b.close()
    if allow_reset:
        b = connect(importer, app)
        b.sendall(request(CMD_RESET))
        status, length, _flags = response(b)
        check(status == 0, "a reset after the disconnect was refused: %s" % error_text(b, length))
        b.close()
    a.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cards", default="0,1", help="the owner and importer card indices (default 0,1)")
    parser.add_argument("--app", default=APP, help="the TinyGPU binary that runs the servers")
    parser.add_argument("--allow-reset", action="store_true", help="also prove disconnect releases the mapping (resets the second card)")
    args = parser.parse_args(argv)
    try:
        owner, importer = (int(part) for part in args.cards.split(","))
        run((owner, importer), args.app, args.allow_reset)
    except (SmokeFailed, ValueError) as exc:
        print("import failed: %s" % exc, file=sys.stderr)
        return 1
    print("import ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
