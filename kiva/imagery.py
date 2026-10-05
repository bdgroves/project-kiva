"""
USDA NAIP aerial photography for a site window, from Microsoft's Planetary
Computer (public, signed on the fly, no account). Used for the "what you'd
see from a plane" half of the before/after renders.
"""
from __future__ import annotations

import numpy as np
from rasterio.warp import Resampling, reproject

from kiva.fetch import lonlat_bounds


def naip(site, dst_transform, shape, log=print):
    """NAIP RGB (uint8, H x W x 3) on the DTM grid, newest year first,
    older years filling any gaps. Returns (rgb, year) or (None, None)."""
    import planetary_computer
    import pystac_client
    import rasterio

    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                    modifier=planetary_computer.sign_inplace)
    items = list(cat.search(collections=["naip"], bbox=lonlat_bounds(site)).items())
    if not items:
        return None, None
    items.sort(key=lambda it: it.datetime, reverse=True)
    out = np.zeros((3,) + shape, np.uint8)
    have = np.zeros(shape, bool)
    years = []
    for it in items:
        with rasterio.open(it.assets["image"].href) as src:
            band = np.zeros((3,) + shape, np.uint8)
            for b in range(3):
                reproject(rasterio.band(src, b + 1), band[b], dst_transform=dst_transform,
                          dst_crs=site["crs"], resampling=Resampling.bilinear, dst_nodata=0)
        got = band.max(axis=0) > 0
        new = got & ~have
        if new.any():
            out[:, new] = band[:, new]
            have |= new
            years.append(it.datetime.year)
        if have.mean() > 0.995:
            break
    log(f"  NAIP {sorted(set(years), reverse=True)}: {have.mean():.1%} covered")
    return np.moveaxis(out, 0, -1), (max(years) if years else None)
