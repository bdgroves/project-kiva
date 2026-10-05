"""
Products -> web layers.

Each layer is reprojected to Web Mercator (what Leaflet draws in), so a plain
L.imageOverlay lines up with the basemap, and written as WebP with
transparency where there is no data.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds

MAX_PX = 2400

# Diverging ramp for local relief: hollows blue, bumps warm, zero transparent-ish.
LRM_STOPS = [(-1.0, (38, 84, 148)), (-0.35, (110, 160, 205)), (0.0, (238, 232, 218)),
             (0.35, (230, 150, 80)), (1.0, (150, 45, 20))]


def to_mercator(arr, prof):
    src_crs, src_t = prof["crs"], prof["transform"]
    H, W = arr.shape
    dst_t, dw, dh = calculate_default_transform(src_crs, "EPSG:3857", W, H,
                                                *array_bounds(H, W, src_t))
    k = max(dw, dh) / MAX_PX
    if k > 1:
        dst_t = dst_t * dst_t.scale(k, k)
        dw, dh = int(round(dw / k)), int(round(dh / k))
    out = np.full((dh, dw), np.nan, np.float32)
    reproject(arr, out, src_transform=src_t, src_crs=src_crs, dst_transform=dst_t,
              dst_crs="EPSG:3857", resampling=Resampling.bilinear,
              src_nodata=np.nan, dst_nodata=np.nan)
    w, s, e, n = transform_bounds("EPSG:3857", "EPSG:4326", *array_bounds(dh, dw, dst_t))
    return out, [[s, w], [n, e]]


def ramp(t, stops):
    t = np.clip(t, stops[0][0], stops[-1][0])
    out = np.zeros(t.shape + (3,), np.float32)
    for (v0, c0), (v1, c1) in zip(stops[:-1], stops[1:]):
        m = (t >= v0) & (t <= v1)
        w = ((t - v0) / (v1 - v0))[m][:, None]
        out[m] = np.array(c0) * (1 - w) + np.array(c1) * w
    return out


def grey_rgba(a, lo, hi, gamma=1.0):
    t = np.clip((a - lo) / (hi - lo), 0, 1) ** gamma
    g = (np.nan_to_num(t) * 255).astype(np.uint8)
    alpha = np.where(np.isfinite(a), 255, 0).astype(np.uint8)
    return np.dstack([g, g, g, alpha])


def lrm_rgba(lrm, clip):
    t = lrm / clip
    rgb = ramp(np.nan_to_num(t), LRM_STOPS)
    alpha = np.where(np.isfinite(lrm), 235, 0).astype(np.uint8)
    return np.dstack([rgb.astype(np.uint8), alpha])


def save_webp(rgba, path: Path, quality=82):
    Image.fromarray(rgba, "RGBA").save(path, "WEBP", quality=quality, method=6)


def robust(a, p=99.0):
    v = np.abs(a[np.isfinite(a)])
    return float(np.percentile(v, p)) if v.size else 1.0


def export(products: dict, prof, out_dir: Path) -> dict:
    """Write the web layers and return their metadata."""
    out_dir.mkdir(parents=True, exist_ok=True)
    layers, bounds = {}, None
    clip = max(0.15, round(robust(products["lrm"], 98.5), 2))
    def pct(a, lo, hi):
        v = a[np.isfinite(a)]
        return (float(np.percentile(v, lo)), float(np.percentile(v, hi))) if v.size else (0.0, 1.0)
    c_lo, c_hi = pct(products["composite"], 0.5, 99.0)
    h_lo, h_hi = pct(products["multi_hillshade"], 0.5, 99.5)
    specs = {
        "composite": (lambda a: grey_rgba(a, c_lo, c_hi, 1.3), "Relief composite (after VAT)"),
        "multi_hillshade": (lambda a: grey_rgba(a, h_lo, h_hi), "Hillshade, 16 directions"),
        "lrm": (lambda a: lrm_rgba(a, clip), f"Local relief, ±{clip:g} m"),
        "svf": (lambda a: grey_rgba(a, 0.80, 1.0, 1.4), "Sky-view factor"),
        "neg_openness": (lambda a: grey_rgba(a, 80.0, 95.0), "Negative openness"),
    }
    for key, (fn, label) in specs.items():
        merc, bounds = to_mercator(products[key], prof)
        save_webp(fn(merc), out_dir / f"{key}.webp")
        layers[key] = {"file": f"{key}.webp", "label": label}
    return {"bounds": bounds, "layers": layers, "lrm_clip_m": clip}


def write_json(obj, path: Path):
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
