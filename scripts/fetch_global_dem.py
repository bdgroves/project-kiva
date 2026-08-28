"""
scripts/fetch_global_dem.py

Fetch Copernicus GLO-30 elevation tiles for sites outside the United States.

USGS 3DEP (used by download_dem.py) is US-only. Copernicus GLO-30 is a global
30 m Digital Surface Model derived from the TanDEM-X radar mission, served as
Cloud Optimized GeoTIFFs from a public AWS bucket -- no account, no API key.

Note this is a DSM, not a bare-earth DTM: it includes buildings, vegetation and
standing monuments. For archaeology that is a feature, not a bug -- the
pyramids at Giza are IN the elevation data.

Usage:
    pixi run python scripts/fetch_global_dem.py --lat 29.9792 --lon 31.1342 --name giza
    pixi run python scripts/fetch_global_dem.py --lat 17.2220 --lon -89.6237 --name tikal
"""

import math
import subprocess
from pathlib import Path

import click
import requests

ROOT = Path(__file__).parent.parent
BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"


def tile_name(lat: float, lon: float) -> str:
    """Copernicus tiles are named by the integer degree of their SW corner."""
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return (f"Copernicus_DSM_COG_10_{ns}{abs(math.floor(lat)):02d}_00"
            f"_{ew}{abs(math.floor(lon)):03d}_00_DEM")


@click.command()
@click.option("--lat", type=float, required=True, help="Latitude of the site")
@click.option("--lon", type=float, required=True, help="Longitude of the site")
@click.option("--name", required=True, help="Short name, used for the filename")
def main(lat, lon, name):
    """Download the Copernicus GLO-30 tile containing a given lat/lon."""
    tile = tile_name(lat, lon)
    url = f"{BUCKET}/{tile}/{tile}.tif"

    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f"{name}_cop30.tif"

    click.echo(f"Site:  {lat}, {lon}")
    click.echo(f"Tile:  {tile}")

    head = requests.head(url, timeout=30)
    if head.status_code != 200:
        click.echo(f"Tile not available (HTTP {head.status_code}).", err=True)
        click.echo("Ocean tiles and some gaps are genuinely absent from the bucket.")
        raise SystemExit(1)

    size_mb = int(head.headers.get("content-length", 0)) / 1e6
    click.echo(f"Size:  {size_mb:.1f} MB")

    if dest.exists():
        click.echo(f"Already downloaded: {dest}")
        return

    click.echo("Downloading...")
    subprocess.run(["curl.exe", "-L", "--progress-bar", "-o", str(dest), url], check=True)
    click.echo(f"Saved: {dest}")
    click.echo()
    click.echo("Next: crop to your area of interest, reproject to a metric CRS, then:")
    click.echo(f"  pixi run python scripts/render_site.py --dem <cropped.tif>")


if __name__ == "__main__":
    main()
