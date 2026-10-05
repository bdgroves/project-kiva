"""
Archaeological relief visualisation from a bare-earth DTM.

Every product here answers the same problem: a 40 cm wall stub is invisible
next to a 100 m canyon wall, because ordinary shading is dominated by the big
landforms. Each method strips the big shape away in a different way.

    hillshade      one sun direction; the familiar look, and the most biased
    multi_hillshade 16 suns averaged: no direction hides a feature
    slope          steepness, independent of any light
    local_relief   DTM minus a smoothed copy of itself (a simple Local Relief
                   Model, after Hesse 2010): only the small bumps survive
    sky_view       how much of the sky each cell can see (Zakšek et al. 2011);
                   ditches and kiva pits see less sky, ridges see more
    openness       positive / negative openness (Yokoyama et al. 2002), the
                   same horizon scan read as angles
    composite      a blend of the above after VAT (Kokalj & Somrak 2019),
                   the archaeologists' all-purpose view

All functions take a float32 DTM with NaN for nodata and a cell size in metres.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter, distance_transform_edt


def fill_nodata(dem: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Nearest-neighbour fill so the filters have something to chew on.
    Returns (filled, mask_of_original_nodata)."""
    bad = ~np.isfinite(dem)
    if not bad.any():
        return dem.astype(np.float32), bad
    idx = distance_transform_edt(bad, return_distances=False, return_indices=True)
    return dem[tuple(idx)].astype(np.float32), bad


def _gradients(dem, res):
    # rows run north -> south, so dz/dy (north positive) is minus the row gradient
    gy, gx = np.gradient(dem, res)
    return gx, -gy


def hillshade(dem, res, azimuth=315.0, altitude=35.0, z=1.0):
    gx, gy = _gradients(dem * z, res)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, -gy)            # direction the slope faces, from north
    az, alt = np.radians(azimuth), np.radians(altitude)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(hs, 0, 1).astype(np.float32)


def multi_hillshade(dem, res, n=16, altitude=35.0):
    out = np.zeros_like(dem, dtype=np.float32)
    for az in np.arange(n) * (360.0 / n):
        out += hillshade(dem, res, az, altitude)
    return out / n


def slope(dem, res):
    gx, gy = _gradients(dem, res)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)


def local_relief(dem, res, radius_m=15.0):
    """DTM minus a Gaussian-smoothed DTM. sigma = radius / 2 keeps features
    up to roughly `radius_m` across and removes the landforms bigger than that."""
    return (dem - gaussian_filter(dem, sigma=radius_m / res / 2.0)).astype(np.float32)


def horizon_scan(dem, res, radius_m=10.0, n_dir=16):
    """Highest horizon angle in each of n_dir directions, out to radius_m.
    Returns (max_up, max_down): arrays (n_dir, H, W) of radians for the
    terrain as-is and turned upside down (for negative openness)."""
    H, W = dem.shape
    steps = max(2, int(round(radius_m / res)))
    pad = steps + 1
    big = np.pad(dem, pad, mode="edge")
    up = np.full((n_dir, H, W), -np.pi / 2, np.float32)
    dn = np.full((n_dir, H, W), -np.pi / 2, np.float32)
    for k in range(n_dir):
        a = 2 * np.pi * k / n_dir
        dx, dy = np.sin(a), -np.cos(a)       # east, and rows go south
        for s in range(1, steps + 1):
            ox, oy = int(round(dx * s)), int(round(dy * s))
            dist = res * np.hypot(ox, oy)
            if dist == 0:
                continue
            nb = big[pad + oy:pad + oy + H, pad + ox:pad + ox + W]
            d = nb - dem
            np.maximum(up[k], np.arctan(d / dist), out=up[k])
            np.maximum(dn[k], np.arctan(-d / dist), out=dn[k])
    return up, dn


def sky_view(up):
    """Sky-View Factor: 1 is a flat plain (all the sky), less is enclosed."""
    return (1.0 - np.mean(np.sin(np.clip(up, 0, None)), axis=0)).astype(np.float32)


def openness(up, dn):
    """Positive openness is high on ridges and wall tops; negative openness is
    high in ditches, pits and room depressions. Degrees."""
    pos = np.degrees(np.mean(np.pi / 2 - up, axis=0)).astype(np.float32)
    neg = np.degrees(np.mean(np.pi / 2 - dn, axis=0)).astype(np.float32)
    return pos, neg


def stretch(a, lo, hi):
    return np.clip((a - lo) / (hi - lo), 0, 1).astype(np.float32)


def composite(hs, slp, svf, pos):
    """After VAT, 'general' settings (Kokalj & Somrak 2019). From the bottom:
    hillshade (normal), slope inverted 0-51 deg (luminosity, 50%),
    positive openness 75-95 deg (overlay, 50%), sky-view 0.65-1 (multiply, 25%).
    All greyscale, so luminosity is a plain mix."""
    base = hs
    s = 1.0 - stretch(slp, 0.0, 51.0)
    base = base * 0.5 + s * 0.5
    o = stretch(pos, 75.0, 95.0)
    ov = np.where(base < 0.5, 2 * base * o, 1 - 2 * (1 - base) * (1 - o))
    base = base * 0.5 + ov * 0.5
    v = stretch(svf, 0.65, 1.0)
    base = base * 0.75 + (base * v) * 0.25
    return np.clip(base, 0, 1).astype(np.float32)


def all_products(dem, res, lrm_radius_m=15.0, horizon_m=10.0):
    """Everything at once from a DTM with NaN nodata."""
    filled, bad = fill_nodata(dem)
    hs = hillshade(filled, res)
    mhs = multi_hillshade(filled, res)
    slp = slope(filled, res)
    lrm = local_relief(filled, res, lrm_radius_m)
    up, dn = horizon_scan(filled, res, horizon_m)
    svf = sky_view(up)
    pos, neg = openness(up, dn)
    del up, dn
    comp = composite(hs, slp, svf, pos)
    out = dict(hillshade=hs, multi_hillshade=mhs, slope=slp, lrm=lrm,
               svf=svf, pos_openness=pos, neg_openness=neg, composite=comp)
    for v in out.values():
        v[bad] = np.nan
    return out
