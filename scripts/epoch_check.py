"""
scripts/epoch_check.py

Before differencing two DEM "epochs", check they are actually different data.

USGS 3DEP seamless tiles are republished whenever ANY source project inside
the 1-degree tile is refreshed. The publication date therefore says nothing
about when your particular pixels were surveyed, and consecutive publications
are frequently byte-identical over the area you care about.

This script pulls the same window from every published epoch of a tile via
COG range-request, reports which ones are pixel-identical, and for the pairs
that do differ, runs a radial stable-ground check: if far-field terrain
disagrees as much as your target does, the signal is a source artefact, not
change on the ground.

    pixi run python scripts/epoch_check.py --tile n47w123 \
        --west -122.225 --east -122.165 --south 46.165 --north 46.215
"""
import itertools
from pathlib import Path

import click
import numpy as np
import rasterio
import requests
from rasterio.windows import from_bounds

ROOT = Path(__file__).parent.parent
TNM = "https://tnmaccess.nationalmap.gov/api/v1/products"
S3 = ("https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/"
      "TIFF/historical/{tile}/USGS_13_{tile}_{epoch}.tif")


def list_epochs(west, south, east, north):
    """Every published 1/3 arc-second epoch overlapping the window."""
    r = requests.get(TNM, params={
        "datasets": "National Elevation Dataset (NED) 1/3 arc-second",
        "bbox": f"{west},{south},{east},{north}",
        "outputFormat": "JSON", "max": 20}, timeout=90)
    out = []
    for it in r.json().get("items", []):
        title = it.get("title", "")
        if "1/3 Arc Second" not in title:
            continue
        out.append({
            "epoch": title.split()[-1],
            "published": it.get("publicationDate"),
            # NOTE: this is the *triggering* source project's survey window,
            # somewhere in the 1-degree tile. Not necessarily your pixels.
            "vendor": (it.get("vendorMetaUrl") or "").rsplit("/", 1)[-1][:60],
        })
    return sorted(out, key=lambda d: d["epoch"])


@click.command()
@click.option("--tile", required=True, help="e.g. n47w123")
@click.option("--west", type=float, required=True)
@click.option("--east", type=float, required=True)
@click.option("--south", type=float, required=True)
@click.option("--north", type=float, required=True)
@click.option("--cache", default="data/processed/epoch_check", show_default=True)
def main(tile, west, east, south, north, cache):
    """Report which published epochs of a 3DEP tile actually differ."""
    outdir = ROOT / cache
    outdir.mkdir(parents=True, exist_ok=True)

    epochs = list_epochs(west, south, east, north)
    if not epochs:
        raise SystemExit("no epochs returned")
    click.echo(f"{len(epochs)} published epochs for {tile}:")
    for e in epochs:
        click.echo(f"  {e['epoch']}  published {e['published']}  <- {e['vendor']}")

    arrs, res = {}, None
    for e in epochs:
        tag = e["epoch"]
        dst = outdir / f"{tile}_{tag}.tif"
        if not dst.exists():
            # COG range-request: only the bytes for this window cross the wire
            with rasterio.open(S3.format(tile=tile, epoch=tag)) as src:
                win = from_bounds(west, south, east, north, src.transform)
                data = src.read(1, window=win)
                prof = src.profile.copy()
                prof.update(height=data.shape[0], width=data.shape[1],
                            transform=src.window_transform(win),
                            compress="deflate")
            with rasterio.open(dst, "w", **prof) as dstf:
                dstf.write(data, 1)
        with rasterio.open(dst) as src:
            arrs[tag] = src.read(1).astype(np.float64)
            res = src.res

    click.echo("\npairwise comparison over the requested window:")
    distinct = []
    for a, b in itertools.combinations(sorted(arrs), 2):
        same = np.array_equal(arrs[a], arrs[b])
        flag = "IDENTICAL" if same else f"differs, max|d|={np.abs(arrs[b]-arrs[a]).max():.1f} m"
        click.echo(f"  {a} vs {b}: {flag}")
        if not same:
            distinct.append((a, b))

    if not distinct:
        click.echo("\nAll epochs identical here. There is no time series to analyse.")
        return

    # stable-ground check on the largest-signal pair
    a, b = max(distinct, key=lambda p: np.abs(arrs[p[1]] - arrs[p[0]]).max())
    d = arrs[b] - arrs[a]
    ny, nx = d.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    cy, cx = np.unravel_index(np.argmax(np.abs(d)), d.shape)
    lat = (north + south) / 2
    mx = abs(res[0]) * 111320 * np.cos(np.radians(lat))
    my = abs(res[1]) * 110540
    r_m = np.sqrt(((xx - cx) * mx) ** 2 + ((yy - cy) * my) ** 2)

    click.echo(f"\nstable-ground check, {a} -> {b}, rings from peak-change pixel:")
    click.echo("  ring (m)        n    median d     p95|d|")
    for lo, hi in [(0,400),(400,800),(800,1200),(1200,1800),(1800,2500),(2500,3500),(3500,5000)]:
        m = (r_m >= lo) & (r_m < hi)
        if not m.any():
            continue
        dd = d[m]
        click.echo(f"  {lo:5d}-{hi:<5d} {m.sum():7d} {np.median(dd):10.2f} "
                   f"{np.percentile(np.abs(dd),95):10.2f}")
    click.echo("\nIf the far rings are near zero, the near-field signal is real.")
    click.echo("If they are not, you are looking at a source change, not ground change.")


if __name__ == "__main__":
    main()
