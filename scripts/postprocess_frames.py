"""
scripts/postprocess_frames.py

forge3d's terrain shading is colormap-driven, so raw frames come out low
contrast. This re-grades them: luminance -> unsharp -> fixed global stretch
-> palette.

The stretch bounds are computed ONCE across a sample of frames and reused for
every frame. Per-frame normalisation would make the histogram breathe and the
finished clip would flicker.

    pixi run python scripts/postprocess_frames.py --palette steel
    pixi run python scripts/postprocess_frames.py --palette volcanic
"""
from pathlib import Path

import click
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).parent.parent
LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)

PALETTES = {
    # cool blue-grey; good for coastal / built structures
    "steel": [
        (0.00, (10,  16,  30)), (0.22, (34,  52,  78)),
        (0.45, (86, 110, 138)), (0.70, (158, 180, 198)),
        (0.88, (214, 228, 238)), (1.00, (250, 253, 255)),
    ],
    # basalt -> ash -> snow; good for volcanic terrain
    "volcanic": [
        (0.00, (16,  12,  14)), (0.20, (58,  44,  44)),
        (0.42, (112, 88,  78)), (0.62, (168, 142, 124)),
        (0.80, (212, 198, 188)), (1.00, (255, 253, 250)),
    ],
    # umber to bone; good for earthworks and mound sites
    "earth": [
        (0.00, (22,  17,  13)), (0.22, (70,  50,  36)),
        (0.45, (128, 98,  68)), (0.68, (184, 154, 116)),
        (0.86, (224, 205, 175)), (1.00, (251, 245, 234)),
    ],
    # warm sand; good for desert sites
    "desert": [
        (0.00, (92,  66,  44)), (0.30, (150, 112, 70)),
        (0.55, (192, 156, 104)), (0.78, (225, 198, 152)),
        (1.00, (252, 246, 232)),
    ],
    "mono": [
        (0.00, (8, 8, 8)), (0.5, (128, 128, 128)), (1.00, (252, 252, 252)),
    ],
}


def ramp(t, stops):
    out = np.zeros(t.shape + (3,), dtype=np.float32)
    for i in range(len(stops) - 1):
        v0, c0 = stops[i]
        v1, c1 = stops[i + 1]
        m = (t >= v0) & (t <= v1)
        if not m.any():
            continue
        w = ((t - v0) / (v1 - v0 + 1e-8))[m][:, None]
        out[m] = np.array(c0, np.float32) * (1 - w) + np.array(c1, np.float32) * w
    return out


@click.command()
@click.option("--src", default="data/renders/frames_raw", show_default=True)
@click.option("--dst", default="data/renders/frames_final", show_default=True)
@click.option("--palette", type=click.Choice(sorted(PALETTES)), default="steel",
              show_default=True)
@click.option("--unsharp", default=1.15, show_default=True,
              help="Unsharp mask strength; raises fine relief")
@click.option("--gamma", default=0.85, show_default=True)
def main(src, dst, palette, unsharp, gamma):
    """Grade a raw frame sequence with flicker-free fixed contrast bounds."""
    srcd, dstd = ROOT / src, ROOT / dst
    dstd.mkdir(parents=True, exist_ok=True)
    frames = sorted(srcd.glob("frame_*.png"))
    if not frames:
        raise SystemExit(f"no frames in {srcd}")
    click.echo(f"{len(frames)} frames | palette={palette}")

    # pass 1: global stretch bounds from a sample -> no flicker
    vals = []
    for f in frames[::12]:
        a = np.asarray(Image.open(f).convert("RGB"), np.float32) / 255.0
        vals.append((a @ LUMA).ravel()[::7])
    allv = np.concatenate(vals)
    lo, hi = np.percentile(allv, 0.5), np.percentile(allv, 99.5)
    click.echo(f"global stretch: {lo:.4f} -> {hi:.4f}")

    stops = PALETTES[palette]
    for i, f in enumerate(frames):
        rgb = np.asarray(Image.open(f).convert("RGB"), np.float32) / 255.0
        lum = rgb @ LUMA
        lum = np.clip(lum + unsharp * (lum - gaussian_filter(lum, sigma=2.0)), 0, 1)
        t = np.clip((lum - lo) / (hi - lo + 1e-8), 0, 1) ** gamma
        Image.fromarray(ramp(t, stops).astype(np.uint8)).save(dstd / f.name)
        if i % 40 == 0:
            click.echo(f"  {i}/{len(frames)}")
    click.echo(f"graded -> {dstd}")


if __name__ == "__main__":
    main()
