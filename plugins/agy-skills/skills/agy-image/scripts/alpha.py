#!/usr/bin/env python3
"""Turn a flat-background image into a transparent PNG. No third-party dependencies required.

Modes (choose the one matching how the image was generated):
  black   image drawn on pure black: alpha = brightness. Ideal for neon / glow / light line art.
          Compositing the result over any background reproduces an additive ("screen") glow.
  white   image drawn on pure white: alpha = darkness. For dark ink / line drawings.
  chroma  image drawn on a flat magenta background: alpha = distance from the background color
          (measured from the image border, not assumed to be #FF00FF), with despill.
          For full-color subjects (photos, colored flat illustrations).

Decoding: Pillow if available; otherwise macOS `sips` converts to PNG and a small pure-Python
PNG reader/writer handles the pixels (8-bit RGB/RGBA, non-interlaced).

CLI: alpha.py in.jpg out.png --mode black [--trim] [--pad 8]
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile
import zlib

MODES = ("black", "white", "chroma")
KEY = (255, 0, 255)  # magenta


# ---------- pixel I/O ----------

def _load_pillow(path):
    from PIL import Image  # type: ignore
    im = Image.open(path).convert("RGB")
    return im.size[0], im.size[1], bytearray(im.tobytes())


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _load_png_stdlib(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, w = 8, [], None
    while pos < len(data):
        (ln,) = struct.unpack(">I", data[pos:pos + 4])
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (2, 6) or interlace != 0:
                raise ValueError(f"unsupported PNG (depth={depth}, type={ctype}, interlace={interlace}); pip install pillow")
            bpp = 3 if ctype == 2 else 4
        elif typ == b"IDAT":
            idat.append(body)
        elif typ == b"IEND":
            break
    raw = zlib.decompress(b"".join(idat))
    stride = w * bpp
    out = bytearray(w * h * 3)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        ft = raw[p]
        p += 1
        cur = bytearray(raw[p:p + stride])
        p += stride
        if ft == 1:
            for i in range(bpp, stride):
                cur[i] = (cur[i] + cur[i - bpp]) & 255
        elif ft == 2:
            for i in range(stride):
                cur[i] = (cur[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                left = cur[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                left = cur[i - bpp] if i >= bpp else 0
                ul = prev[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + _paeth(left, prev[i], ul)) & 255
        elif ft != 0:
            raise ValueError("bad PNG filter")
        if bpp == 3:
            out[y * w * 3:(y + 1) * w * 3] = cur
        else:
            row = out[y * w * 3:(y + 1) * w * 3]
            for x in range(w):
                row[x * 3:x * 3 + 3] = cur[x * 4:x * 4 + 3]
            out[y * w * 3:(y + 1) * w * 3] = row
        prev = cur
    return w, h, out


def load_rgb(path):
    """Return (w, h, bytearray RGB)."""
    try:
        return _load_pillow(path)
    except ImportError:
        pass
    if path.lower().endswith(".png"):
        return _load_png_stdlib(path)
    if not _which("sips"):
        sys.exit("Need Pillow (pip install pillow) or macOS sips to decode images.")
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
    subprocess.run(["sips", "-s", "format", "png", path, "--out", tmp], check=True, capture_output=True)
    try:
        return _load_png_stdlib(tmp)
    finally:
        os.unlink(tmp)


def _which(cmd):
    from shutil import which
    return which(cmd)


def save_rgba_png(path, w, h, rgba):
    try:
        from PIL import Image  # type: ignore
        Image.frombytes("RGBA", (w, h), bytes(rgba)).save(path, optimize=True)
        return
    except ImportError:
        pass
    stride = w * 4
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(t, b):
        c = struct.pack(">I", len(b)) + t + b
        return c + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


# ---------- alpha extraction ----------

def border_color(w, h, rgb, step=4):
    """Median color of the outermost pixels. The generator's "flat magenta" is never exactly #FF00FF
    (e.g. RGB(248, 63, 231)), so the key color must be measured, not assumed."""
    samples = []
    for x in range(0, w, step):
        for y in (0, h - 1):
            i = (y * w + x) * 3; samples.append(rgb[i:i + 3])
    for y in range(0, h, step):
        for x in (0, w - 1):
            i = (y * w + x) * 3; samples.append(rgb[i:i + 3])
    med = lambda k: sorted(p[k] for p in samples)[len(samples) // 2]
    return (med(0), med(1), med(2))


def to_rgba(w, h, rgb, mode, gamma=1.0, low=0, high=255, floor=16):
    """Build RGBA. low/high: alpha ramp endpoints (values below low -> 0, above high -> 255).
    floor: alpha values below this become 0, which removes JPEG speckle on the flat background."""
    n = w * h
    rgba = bytearray(n * 4)
    key = border_color(w, h, rgb) if mode == "chroma" else KEY
    span = max(1, high - low)
    lut = bytearray(256)
    for v in range(256):
        a = min(255, max(0, (v - low) * 255 // span))
        if gamma != 1.0:
            a = int(255 * ((a / 255.0) ** gamma) + 0.5)
        lut[v] = a
    for i in range(n):
        r, g, b = rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]
        if mode == "black":
            a = lut[max(r, g, b)]
            if a:  # un-premultiply so color stays saturated when composited over light backgrounds
                s = 255 / a
                r, g, b = min(255, int(r * s)), min(255, int(g * s)), min(255, int(b * s))
        elif mode == "white":
            a = lut[255 - min(r, g, b)]
            if a:
                # treat as ink over white: c = 255 - (255 - c) * 255 / a
                s = 255 / a
                r = max(0, 255 - int((255 - r) * s))
                g = max(0, 255 - int((255 - g) * s))
                b = max(0, 255 - int((255 - b) * s))
        else:  # chroma (magenta)
            d = ((r - key[0]) ** 2 + (g - key[1]) ** 2 + (b - key[2]) ** 2) ** 0.5  # 0..~441
            a = lut[min(255, int(d))]
            if 0 < a < 255:
                # despill: pull magenta out of edge pixels
                m = min(r, b)
                if g < m:
                    g = m
        if a < floor:
            a = 0
        o = i * 4
        rgba[o], rgba[o + 1], rgba[o + 2], rgba[o + 3] = r, g, b, a
    return rgba


def bbox(w, h, rgba, thresh=24):
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        row = rgba[y * w * 4 + 3:(y + 1) * w * 4:4]
        for x, a in enumerate(row):
            if a > thresh:
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    return (x0, y0, x1 + 1, y1 + 1) if x1 >= 0 else (0, 0, w, h)


def crop(w, h, rgba, box, pad=0):
    x0, y0, x1, y1 = box
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(w, x1 + pad), min(h, y1 + pad)
    nw, nh = x1 - x0, y1 - y0
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        src = ((y0 + y) * w + x0) * 4
        out[y * nw * 4:(y + 1) * nw * 4] = rgba[src:src + nw * 4]
    return nw, nh, out


def make_transparent(src, dst, mode="black", trim=False, pad=8, low=None, high=None, gamma=1.0):
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    # chroma thresholds are distances from the measured border color; JPEG noise there stays under ~15
    defaults = {"black": (6, 235), "white": (6, 235), "chroma": (28, 100)}
    lo, hi = defaults[mode]
    if low is not None: lo = low
    if high is not None: hi = high
    w, h, rgb = load_rgb(src)
    rgba = to_rgba(w, h, rgb, mode, gamma=gamma, low=lo, high=hi)
    if trim:
        w, h, rgba = crop(w, h, rgba, bbox(w, h, rgba), pad=pad)
    save_rgba_png(dst, w, h, rgba)
    return w, h


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--mode", default="black", choices=MODES)
    ap.add_argument("--trim", action="store_true", help="crop to the opaque bounding box")
    ap.add_argument("--pad", type=int, default=8, help="padding kept around the trimmed box")
    ap.add_argument("--low", type=int, help="alpha ramp start (0-255)")
    ap.add_argument("--high", type=int, help="alpha ramp end (0-255)")
    ap.add_argument("--gamma", type=float, default=1.0, help="alpha gamma (<1 keeps more faint glow)")
    a = ap.parse_args()
    w, h = make_transparent(a.src, a.dst, a.mode, a.trim, a.pad, a.low, a.high, a.gamma)
    print(f"{a.dst} {w}x{h}")


if __name__ == "__main__":
    main()
