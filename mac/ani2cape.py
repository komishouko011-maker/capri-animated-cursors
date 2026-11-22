#!/usr/bin/env python3
"""Convert the Capri Windows .ani cursors into a Mousecape .cape for macOS.

Pure standard-library Python 3 (no Pillow needed). Run from anywhere:

    python3 mac/ani2cape.py            # writes mac/Capri.cape
    python3 mac/ani2cape.py --preview  # also writes PNG sprite strips to mac/preview/

How it works
------------
* An .ani file is a RIFF "ACON" container: an `anih` header, a list of
  frames (each one a Windows .cur/.ico file), plus optional `seq ` (frame
  order) and `rate` (per-step duration in 1/60 s "jiffies") chunks.
* Mousecape wants each cursor as one tall image with all frames stacked
  vertically, a single constant frame duration, at most 24 frames, and a
  hotspot measured in points. We store a 32x32 pt cursor with a 1x (32 px)
  and a 2x (64 px) image, so it stays sharp on Retina screens.
* Variable per-frame timings are kept exact by repeating frames on a common
  time step (the GCD of all step durations), as long as that fits in
  24 frames; otherwise we pick the smallest step that fits and round.
"""

import argparse
import math
import os
import plistlib
import struct
import sys
import zlib
from functools import reduce

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

POINTS = 32          # cursor size in points
SCALES = (1, 2)      # 1x and 2x (Retina) representations
MAX_FRAMES = 24      # CoreGraphics limit for animated cursors

# Which macOS cursor slots each Windows cursor fills.
# Identifiers are the ones Mousecape uses; ArrowS/IBeamS are the extra
# variants macOS 26 (Tahoe) looks up.
MAPPING = {
    "NormalSelect.ani": [
        "com.apple.coregraphics.Arrow",
        "com.apple.coregraphics.ArrowS",
    ],
    "text select.ani": [
        "com.apple.coregraphics.IBeam",
        "com.apple.coregraphics.IBeamS",
        "com.apple.coregraphics.IBeamXOR",
    ],
    "LinkSelect.ani": [
        "com.apple.cursor.13",  # Pointing hand (links)
    ],
    "Busy.ani": [
        "com.apple.coregraphics.Wait",  # spinning wait cursor
        "com.apple.cursor.4",           # Busy
    ],
    "Move.ani": [
        "com.apple.coregraphics.Move",
        "com.apple.cursor.39",  # Resize Square (4-way move)
    ],
    "horizontal.ani": [
        "com.apple.cursor.17", "com.apple.cursor.18", "com.apple.cursor.19",  # Resize W / E / W-E
        "com.apple.cursor.27", "com.apple.cursor.28", "com.apple.cursor.38",  # Window E / E-W / W
    ],
    "vertical.ani": [
        "com.apple.cursor.21", "com.apple.cursor.22", "com.apple.cursor.23",  # Resize N / S / N-S
        "com.apple.cursor.31", "com.apple.cursor.32", "com.apple.cursor.36",  # Window N / N-S / S
    ],
    "diagonal resize1.ani": [  # NW-SE
        "com.apple.cursor.33", "com.apple.cursor.34", "com.apple.cursor.35",  # Window NW / NW-SE / SE
    ],
    "diagonal resize2.ani": [  # NE-SW
        "com.apple.cursor.29", "com.apple.cursor.30", "com.apple.cursor.37",  # Window NE / NE-SW / SW
    ],
}


# --------------------------------------------------------------------------
# Image helpers. An image is (width, height, bytearray of RGBA8, row-major).
# --------------------------------------------------------------------------

def png_decode(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, palette, trns = 8, bytearray(), None, None
    while pos < len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            w, h, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif ctype == b"PLTE":
            palette = body
        elif ctype == b"tRNS":
            trns = body
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            break
    if depth != 8 or interlace:
        raise ValueError("unsupported PNG (depth %d, interlace %d)" % (depth, interlace))
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    raw = zlib.decompress(bytes(idat))
    stride = w * channels
    out = bytearray(stride * h)
    prev = bytearray(stride)
    i = 0
    for y in range(h):
        ftype = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - channels] if x >= channels else 0
            b = prev[x]
            c = prev[x - channels] if x >= channels else 0
            if ftype == 1:
                line[x] = (line[x] + a) & 255
            elif ftype == 2:
                line[x] = (line[x] + b) & 255
            elif ftype == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[x] = (line[x] + pred) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    rgba = bytearray(w * h * 4)
    for p in range(w * h):
        if color == 6:
            rgba[p * 4:p * 4 + 4] = out[p * 4:p * 4 + 4]
        elif color == 2:
            rgba[p * 4:p * 4 + 4] = out[p * 3:p * 3 + 3] + b"\xff"
        elif color == 0:
            g = out[p]
            rgba[p * 4:p * 4 + 4] = bytes((g, g, g, 255))
        elif color == 4:
            g, al = out[p * 2], out[p * 2 + 1]
            rgba[p * 4:p * 4 + 4] = bytes((g, g, g, al))
        elif color == 3:
            idx = out[p]
            al = trns[idx] if trns is not None and idx < len(trns) else 255
            rgba[p * 4:p * 4 + 4] = palette[idx * 3:idx * 3 + 3] + bytes((al,))
    return w, h, rgba


def png_encode(img):
    w, h, rgba = img
    rows = b"".join(b"\x00" + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))

    def chunk(t, body):
        return struct.pack(">I", len(body)) + t + body + struct.pack(">I", zlib.crc32(t + body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9))
            + chunk(b"IEND", b""))


def dib_decode(data, w, h):
    """Decode a BMP-in-ICO image (BITMAPINFOHEADER, XOR bitmap + AND mask)."""
    hdr_size, bw, bh2, _, bpp = struct.unpack("<IiiHH", data[:16])
    if bw != w:
        w = bw
    h = abs(bh2) // 2
    colors_used = struct.unpack("<I", data[32:36])[0]
    off = hdr_size
    palette = []
    if bpp <= 8:
        n = colors_used or (1 << bpp)
        palette = [data[off + i * 4:off + i * 4 + 4] for i in range(n)]
        off += n * 4
    xor_stride = ((w * bpp + 31) // 32) * 4
    and_stride = ((w + 31) // 32) * 4
    and_off = off + xor_stride * h
    rgba = bytearray(w * h * 4)
    any_alpha = False
    for y in range(h):
        src_row = off + (h - 1 - y) * xor_stride  # bottom-up
        for x in range(w):
            if bpp == 32:
                b, g, r, a = data[src_row + x * 4:src_row + x * 4 + 4]
                any_alpha |= a != 0
            elif bpp == 24:
                b, g, r = data[src_row + x * 3:src_row + x * 3 + 3]
                a = 255
            elif bpp in (1, 4, 8):
                bit = x * bpp
                byte = data[src_row + bit // 8]
                idx = (byte >> (8 - bpp - bit % 8)) & ((1 << bpp) - 1)
                b, g, r = palette[idx][:3]
                a = 255
            else:
                raise ValueError("unsupported BMP bit depth %d" % bpp)
            rgba[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((r, g, b, a))
    if bpp < 32 or not any_alpha:
        # Fall back to the 1-bit AND mask for transparency.
        for y in range(h):
            row = and_off + (h - 1 - y) * and_stride
            for x in range(w):
                masked = (data[row + x // 8] >> (7 - x % 8)) & 1
                rgba[(y * w + x) * 4 + 3] = 0 if masked else 255
    return w, h, rgba


def resample(img, nw, nh):
    """Area-average resample with premultiplied alpha (good for downscaling)."""
    w, h, src = img
    if (w, h) == (nw, nh):
        return img
    out = bytearray(nw * nh * 4)
    sx, sy = w / nw, h / nh
    for oy in range(nh):
        y0, y1 = oy * sy, (oy + 1) * sy
        for ox in range(nw):
            x0, x1 = ox * sx, (ox + 1) * sx
            acc = [0.0, 0.0, 0.0, 0.0]
            area = 0.0
            for iy in range(int(y0), min(h, math.ceil(y1))):
                wy = min(y1, iy + 1) - max(y0, iy)
                for ix in range(int(x0), min(w, math.ceil(x1))):
                    wx = min(x1, ix + 1) - max(x0, ix)
                    wgt = wx * wy
                    r, g, b, a = src[(iy * w + ix) * 4:(iy * w + ix) * 4 + 4]
                    af = a / 255.0
                    acc[0] += r * af * wgt
                    acc[1] += g * af * wgt
                    acc[2] += b * af * wgt
                    acc[3] += a * wgt
                    area += wgt
            a = acc[3] / area if area else 0
            if a > 0:
                k = 255.0 / a
                px = (acc[0] / area * k, acc[1] / area * k, acc[2] / area * k, a)
            else:
                px = (0, 0, 0, 0)
            out[(oy * nw + ox) * 4:(oy * nw + ox) * 4 + 4] = bytes(min(255, int(round(v))) for v in px)
    return nw, nh, out


def stack_vertically(imgs):
    w, h = imgs[0][0], imgs[0][1]
    buf = bytearray()
    for iw, ih, px in imgs:
        assert (iw, ih) == (w, h)
        buf += px
    return w, h * len(imgs), buf


# --------------------------------------------------------------------------
# .cur / .ani parsing
# --------------------------------------------------------------------------

def parse_cur(data):
    """Return a list of (width, height, hotspot_x, hotspot_y, image)."""
    _, _, count = struct.unpack("<HHH", data[:6])
    entries = []
    for i in range(count):
        bw, bh, _, _, hx, hy, size, offset = struct.unpack("<BBBBHHII", data[6 + 16 * i:22 + 16 * i])
        blob = data[offset:offset + size]
        w, h = bw or 256, bh or 256
        img = png_decode(blob) if blob[:4] == b"\x89PNG" else dib_decode(blob, w, h)
        entries.append((img[0], img[1], hx, hy, img))
    return entries


def riff_chunks(data, start, end):
    pos = start
    while pos + 8 <= end:
        cid = data[pos:pos + 4]
        size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        yield cid, pos + 8, size
        pos += 8 + size + (size & 1)


def parse_ani(path):
    data = open(path, "rb").read()
    if data[:4] != b"RIFF" or data[8:12] != b"ACON":
        raise ValueError("%s is not an animated cursor" % path)
    frames, seq, rate, header = [], None, None, None
    for cid, off, size in riff_chunks(data, 12, len(data)):
        if cid == b"anih":
            header = struct.unpack("<9I", data[off:off + 36])
        elif cid == b"LIST" and data[off:off + 4] == b"fram":
            for c2, o2, s2 in riff_chunks(data, off + 4, off + size):
                if c2 == b"icon":
                    frames.append(parse_cur(data[o2:o2 + s2]))
        elif cid == b"seq ":
            seq = list(struct.unpack("<%dI" % (size // 4), data[off:off + size]))
        elif cid == b"rate":
            rate = list(struct.unpack("<%dI" % (size // 4), data[off:off + size]))
    _, n_frames, n_steps, _, _, _, _, default_rate, _ = header
    seq = seq or list(range(len(frames)))
    rate = rate or [default_rate] * len(seq)
    return frames, seq, rate


def plan_timeline(seq, rate):
    """Turn (frame order, per-step jiffies) into (frame list, seconds per frame)."""
    rate = [max(1, r) for r in rate]
    unit = reduce(math.gcd, rate)
    while sum(round(r / unit) or 1 for r in rate) > MAX_FRAMES:
        unit += 1
    timeline = []
    for idx, r in zip(seq, rate):
        timeline += [idx] * max(1, round(r / unit))
    return timeline, unit / 60.0


def pick(entries, px):
    """Pick the entry closest to (and preferably at least) `px` pixels wide."""
    exact = [e for e in entries if e[0] == px]
    if exact:
        return exact[0]
    bigger = sorted((e for e in entries if e[0] > px), key=lambda e: e[0])
    return bigger[0] if bigger else max(entries, key=lambda e: e[0])


def convert_cursor(path):
    frames, seq, rate = parse_ani(path)
    timeline, duration = plan_timeline(seq, rate)

    # Hotspot in points. Each size inside a .cur stores its own hotspot and
    # in this pack they disagree a little (and a few are plainly wrong, e.g.
    # Busy's 64 px one sits in the corner), so take the per-axis median.
    def median(vals):
        vals = sorted(vals)
        n = len(vals)
        return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2

    hot_x = median([e[2] * POINTS / e[0] for e in frames[0]])
    hot_y = median([e[3] * POINTS / e[1] for e in frames[0]])

    reps = []
    for scale in SCALES:
        px = POINTS * scale
        sized = []
        for f in frames:
            e = pick(f, px)
            sized.append(resample(e[4], px, px))
        reps.append(stack_vertically([sized[i] for i in timeline]))

    cursor = {
        "FrameCount": len(timeline),
        "FrameDuration": duration,
        "HotSpotX": round(hot_x, 2),
        "HotSpotY": round(hot_y, 2),
        "PointsWide": float(POINTS),
        "PointsHigh": float(POINTS),
        "Representations": [png_encode(r) for r in reps],
    }
    return cursor, reps


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", default=REPO, help="folder with the .ani files (default: repo root)")
    ap.add_argument("--out", default=os.path.join(HERE, "Capri.cape"))
    ap.add_argument("--preview", action="store_true", help="also write PNG sprite strips to mac/preview/")
    args = ap.parse_args()

    cursors = {}
    for fname, ids in MAPPING.items():
        path = os.path.join(args.src, fname)
        if not os.path.exists(path):
            print("skip (missing): %s" % fname, file=sys.stderr)
            continue
        cursor, reps = convert_cursor(path)
        for cid in ids:
            cursors[cid] = cursor
        print("%-22s %2d frames @ %.0f ms, hotspot (%.1f, %.1f) -> %d slots" % (
            fname, cursor["FrameCount"], cursor["FrameDuration"] * 1000,
            cursor["HotSpotX"], cursor["HotSpotY"], len(ids)))
        if args.preview:
            pdir = os.path.join(HERE, "preview")
            os.makedirs(pdir, exist_ok=True)
            base = os.path.splitext(fname)[0].replace(" ", "_")
            with open(os.path.join(pdir, base + "@2x.png"), "wb") as fh:
                fh.write(png_encode(reps[-1]))

    cape = {
        "Author": "komishouko011-maker",
        "CapeName": "Capri Animated",
        "CapeVersion": 1.0,
        "Cloud": False,
        "Cursors": cursors,
        "HiDPI": True,
        "Identifier": "com.komishouko011-maker.capri-animated",
        "MinimumVersion": 2.0,
        "Version": 2.0,
    }
    with open(args.out, "wb") as fh:
        plistlib.dump(cape, fh, fmt=plistlib.FMT_XML)
    print("wrote %s (%d cursor slots)" % (args.out, len(cursors)))


if __name__ == "__main__":
    main()
