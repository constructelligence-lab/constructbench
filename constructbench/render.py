"""A tiny raster canvas and PNG encoder, stdlib only, for the visual-intelligence tasks.

Drawings are rendered from the same numbers the answers are computed from, so the picture and the reference
answer cannot disagree — and a seed reproduces the exact image.
"""
from __future__ import annotations

import base64
import struct
import zlib

# 5×7 glyphs, one string per row, '#' = ink.
_FONT = {
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["####.", "....#", "....#", ".###.", "....#", "....#", "####."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "J": ["..###", "...#.", "...#.", "...#.", "#..#.", "#..#.", ".##.."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    ":": [".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."],
    "=": [".....", ".....", "#####", ".....", "#####", ".....", "....."],
    "/": ["....#", "...#.", "...#.", "..#..", ".#...", ".#...", "#...."],
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
}


class Canvas:
    def __init__(self, w: int, h: int, bg: int = 255):
        self.w, self.h = w, h
        self.px = bytearray([bg]) * (w * h)

    def dot(self, x: int, y: int, v: int = 0) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y * self.w + x] = v

    def fill(self, x0: int, y0: int, x1: int, y1: int, v: int = 0) -> None:
        for y in range(max(0, y0), min(self.h, y1)):
            row = y * self.w
            for x in range(max(0, x0), min(self.w, x1)):
                self.px[row + x] = v

    def line(self, x0: int, y0: int, x1: int, y1: int, v: int = 0, t: int = 1, dash: int = 0) -> None:
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err, n = dx + dy, 0
        while True:
            if not dash or (n // dash) % 2 == 0:
                self.fill(x0 - t // 2, y0 - t // 2, x0 - t // 2 + t, y0 - t // 2 + t, v)
            if x0 == x1 and y0 == y1:
                break
            e2, n = 2 * err, n + 1
            if e2 >= dy:
                err += dy; x0 += sx
            if e2 <= dx:
                err += dx; y0 += sy

    def rect(self, x0: int, y0: int, x1: int, y1: int, v: int = 0, t: int = 1) -> None:
        self.line(x0, y0, x1, y0, v, t); self.line(x1, y0, x1, y1, v, t)
        self.line(x1, y1, x0, y1, v, t); self.line(x0, y1, x0, y0, v, t)

    def circle(self, cx: int, cy: int, r: int, v: int = 0, filled: bool = False, t: int = 1) -> None:
        for y in range(-r - t, r + t + 1):
            for x in range(-r - t, r + t + 1):
                d = (x * x + y * y) ** .5
                if (filled and d <= r) or (not filled and r - t / 2 <= d <= r + t / 2):
                    self.dot(cx + x, cy + y, v)

    def text(self, x: int, y: int, s: str, scale: int = 2, v: int = 0) -> None:
        for ch in s.upper():
            g = _FONT.get(ch, _FONT[" "])
            for gy, row in enumerate(g):
                for gx, c in enumerate(row):
                    if c == "#":
                        self.fill(x + gx * scale, y + gy * scale, x + (gx + 1) * scale, y + (gy + 1) * scale, v)
            x += 6 * scale

    @staticmethod
    def text_width(s: str, scale: int = 2) -> int:
        return len(s) * 6 * scale - scale

    def png(self) -> bytes:
        raw = b"".join(b"\x00" + bytes(self.px[y * self.w:(y + 1) * self.w]) for y in range(self.h))

        def chunk(tag: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 0, 0, 0, 0)       # 8-bit grayscale
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")

    def attachment(self, name: str) -> dict[str, str]:
        return {"name": name, "media_type": "image/png", "data": base64.b64encode(self.png()).decode()}
