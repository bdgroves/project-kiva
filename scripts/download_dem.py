"""
scripts/download_dem.py

Download 1/3 arc-second (10m) GeoTIFF DEMs from USGS 3DEP for any
Project Kiva study area. No account or API key required.

Usage:
    pixi run python scripts/download_dem.py
    pixi run python scripts/download_dem.py --site mesa_verde
    pixi run python scripts/download_dem.py --all
"""

import click
import requests
import yaml
from pathlib import Path
from tqdm import tqdm

# USGS TNM API endpoint
TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"

# 1/3 arc-second (~10m) GeoTIFF — nationwide seamless coverage, always available
# Switch to "National Elevation Dataset (NED) 1 arc-second" for faster/smaller downloads
DATASET = "National Elevation Dataset (NED) 1/3 arc-second"

ROOT = Path(__file__).parent.parent


def load_config():
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def find_tiles(bbox: dict) -> list:
    """Query USGS TNM API for available GeoTIFF tiles in a bounding box."""
    params = {
        "datasets": DATASET,
        "bbox": f"{bbox['west']},{bbox['south']},{bbox['east']},{bbox['north']}",
        "prodFormats": "GeoTIFF",
        "outputFormat": "JSON",
        "max": 20,
    }
    resp = requests.get(TNM_API, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("items", [])


def download_file(url: str, dest: Path, label: str = "") -> Path:
    """Download a file with a progress bar. Skips if already exists."""
    if dest.exists():
        click.echo(f"  Already exists: {dest.name} — skipping")
        return dest

    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))

    with open(dest, "wb") as f, tqdm(
        desc=label or dest.name,
        total=total, unit="B", unit_scale=True, unit_divisor=1024
    ) as bar:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            bar.update(len(chunk))

    return dest


def download_site(site_key: str, cfg: dict) -> list[Path]:
    """Download DEM tiles for a single site. Returns list of downloaded paths."""
    site    = cfg["sites"][site_key]
    bbox    = site["bbox_wgs84"]
    dem_dir = ROOT / cfg["dem"]["output_dir"]
    dem_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"\n{'='*55}")
    click.echo(f"  {site['name']} ({site['state']})")
    click.echo(f"  bbox: {bbox['west']},{bbox['south']} → {bbox['east']},{bbox['north']}")
    click.echo(f"{'='*55}")

    click.echo("Querying USGS TNM API...")
    tiles = find_tiles(bbox)

    if not tiles:
        click.echo("  No tiles found for this bounding box.", err=True)
        click.echo("  Try the manual downloader: https://apps.nationalmap.gov/downloader/")
        return []

    total_mb = sum(t.get("sizeInBytes", 0) for t in tiles) / 1e6
    click.echo(f"  Found {len(tiles)} tile(s)  ({total_mb:.0f} MB total)")

    downloaded = []
    for tile in tiles:
        url      = tile["downloadURL"]
        filename = url.split("/")[-1]
        dest     = dem_dir / f"{site_key}_{filename}"
        click.echo(f"\n  Downloading: {filename}")
        path = download_file(url, dest, label=filename)
        downloaded.append(path)
        click.echo(f"  Saved: {path}")

    return downloaded


@click.command()
@click.option("--site", default=None,
              help="Site key from config.yaml (e.g. chaco, mesa_verde)")
@click.option("--all", "all_sites", is_flag=True,
              help="Download DEMs for all configured sites")
def main(site, all_sites):
    """Download GeoTIFF DEMs from USGS 3DEP for Project Kiva study areas."""
    cfg = load_config()

    if all_sites:
        sites_to_download = list(cfg["sites"].keys())
    elif site:
        if site not in cfg["sites"]:
            click.echo(f"Unknown site: {site}", err=True)
            click.echo(f"Available: {list(cfg['sites'].keys())}")
            raise SystemExit(1)
        sites_to_download = [site]
    else:
        # Default to active site
        sites_to_download = [cfg["active_site"]]

    click.echo(f"Project Kiva — DEM Downloader")
    click.echo(f"Dataset: {DATASET}")
    click.echo(f"Sites: {sites_to_download}")

    all_paths = []
    for sk in sites_to_download:
        paths = download_site(sk, cfg)
        all_paths.extend(paths)

    click.echo(f"\n{'='*55}")
    click.echo(f"Downloaded {len(all_paths)} file(s):")
    for p in all_paths:
        click.echo(f"  {p.name}  ({p.stat().st_size/1e6:.1f} MB)")

    if all_paths:
        click.echo(f"\nNext step: run the render script")
        click.echo(f"  pixi run render --site {sites_to_download[0]}")


if __name__ == "__main__":
    main()
