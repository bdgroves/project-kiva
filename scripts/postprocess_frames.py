"""
scripts/postprocess_frames.py

forge3d's terrain shading is colormap-driven, so raw frames come out low
contrast. This re-grades them: luminance -> unsharp -> fixed global stretch
-> steel palette.

The stretch bounds are computed ONCE across a sample of frames and reused for
every frame. Per-frame normalisation would make the histogram breathe and the
finished clip would flicker.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

SRC = Path("data/renders/frames_raw")
DST = Path("data/renders/frames_final")
DST.mkdir(parents=True, exist_ok=True)

frames = sorted(SRC.glob("frame_*.png"))
print(f"{len(frames)} frames")

LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)

# --- pass 1: global stretch bounds from a sample -------------------------
sample = frames[::12]
vals = []
for f in sample:
    a = np.asarray(Image.open(f).convert("RGB"), dtype=np.float32) / 255.0
    vals.append((a @ LUMA).ravel()[::7])
allv = np.concatenate(vals)
LO, HI = np.percentile(allv, 0.5), np.percentile(allv, 99.5)
print(f"global stretch: {LO:.4f} -> {HI:.4f}")

# --- steel palette ------------------------------------------------------
STOPS = [
    (0.00, (10,  16,  30)),
    (0.22, (34,  52,  78)),
    (0.45, (86, 110, 138)),
    (0.70, (158, 180, 198)),
    (0.88, (214, 228, 238)),
    (1.00, (250, 253, 255)),
]

def grade(rgb):
    lum = rgb @ LUMA
    # unsharp: pull out the fine relief (battery walls, roads, bunker edges)
    blur = gaussian_filter(lum, sigma=2.0)
    lum = np.clip(lum + 1.15 * (lum - blur), 0, 1)

    t = np.clip((lum - LO) / (HI - LO + 1e-8), 0, 1)
    t = t ** 0.85

    out = np.zeros(t.shape + (3,), dtype=np.float32)
    for i in range(len(STOPS) - 1):
        v0, c0 = STOPS[i]
        v1, c1 = STOPS[i + 1]
        m = (t >= v0) & (t <= v1)
        if not m.any():
            continue
        w = ((t - v0) / (v1 - v0 + 1e-8))[m][:, None]
        out[m] = np.array(c0, np.float32) * (1 - w) + np.array(c1, np.float32) * w
    return out

for i, f in enumerate(frames):
    rgb = np.asarray(Image.open(f).convert("RGB"), dtype=np.float32) / 255.0
    Image.fromarray(grade(rgb).astype(np.uint8)).save(DST / f.name)
    if i % 40 == 0:
        print(f"  {i}/{len(frames)}", flush=True)

print("graded ->", DST)
