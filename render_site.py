"""
scripts/render_site.py

Headless forge3d render of any processed DEM in the project.
Uses path_tracing — no interactive_viewer binary required.

Usage:
    pixi run render
    pixi run python scripts/render_site.py --site chaco --samples 128
    pixi run python scripts/render_site.py --dem path/to/custom.tif --out my_render.png
"""

import math
import sys
from pathlib import Path

import click
import numpy as np
import yaml

try:
    import rasterio
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

from forge3d import path_tracing
from forge3d._png import save_png


def load_dem_as_array(dem_path: Path) -> np.ndarray:
    """Load a GeoTIFF DEM as a float32 numpy array."""
    if not HAS_RASTERIO:
        raise RuntimeError("rasterio required to load GeoTIFF — run: pixi install")
    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype(np.float32)
        nodata = src.nodata
    if nodata is not None:
        dem = np.where(dem == nodata, np.nan, dem)
        # Fill NaN with mean to avoid render artifacts
        mean_val = float(np.nanmean(dem))
        dem = np.where(np.isnan(dem), mean_val, dem)
    return dem


def spherical_to_cartesian(phi_deg, theta_deg, radius, look_at):
    """Convert spherical camera params to origin vector."""
    phi   = math.radians(phi_deg)
    theta = math.radians(theta_deg)
    cx, cy, cz = look_at
    ox = cx + radius * math.sin(theta) * math.cos(phi)
    oy = cy + radius * math.sin(theta) * math.sin(phi)
    oz = cz + radius * math.cos(theta)
    return (ox, oy, oz)


def render_dem(
    dem: np.ndarray,
    output_path: str,
    phi_deg: float = 225,
    theta_deg: float = 35,
    radius: float = 1.3,
    sun_az: float = 315,
    sun_el: float = 32,
    width: int = 3840,
    height: int = 2160,
    samples: int = 64,
    max_bounces: int = 2,
):
    """Render a DEM array to PNG using forge3d path tracer."""

    # Normalize DEM to 0-1 range for camera positioning
    dem_min, dem_max = float(np.nanmin(dem)), float(np.nanmax(dem))
    dem_norm = (dem - dem_min) / (dem_max - dem_min + 1e-8)

    rows, cols = dem.shape
    cx = cols / 2.0 / cols   # 0.5
    cy = rows / 2.0 / rows   # 0.5
    cz = float(dem_norm.mean())
    look_at = (cx, cy, cz)

    origin = spherical_to_cartesian(phi_deg, theta_deg, radius, look_at)

    camera = path_tracing.make_camera(
        origin=origin,
        look_at=look_at,
        up=(0.0, 0.0, 1.0),
        fov_y=45.0,
        aspect=width / height,
        exposure=1.0,
    )

    tracer = path_tracing.create_path_tracer(
        width, height,
        max_bounces=max_bounces,
        seed=42,
    )

    click.echo(f"  Rendering {width}×{height} @ {samples} samples...")
    rgba = path_tracing.render_rgba(tracer, dem, camera, samples=samples)
    click.echo(f"  Output: {rgba.shape} {rgba.dtype}")

    save_png(output_path, rgba)
    click.echo(f"  Saved: {output_path}")
    return rgba


@click.command()
@click.option('--site',    default=None, help='Site key from config.yaml (e.g. chaco)')
@click.option('--dem',     default=None, help='Path to DEM GeoTIFF (overrides site lookup)')
@click.option('--out',     default=None, help='Output PNG path')
@click.option('--width',   default=3840, show_default=True)
@click.option('--height',  default=2160, show_default=True)
@click.option('--samples', default=64,   show_default=True, help='Path tracing samples (higher=better quality, slower)')
@click.option('--phi',     default=225.0, show_default=True, help='Camera azimuth degrees')
@click.option('--theta',   default=35.0,  show_default=True, help='Camera elevation degrees')
@click.option('--radius',  default=1.3,   show_default=True, help='Camera distance')
@click.option('--panel',   is_flag=True,  help='Also render 4-angle panel')
def main(site, dem, out, width, height, samples, phi, theta, radius, panel):
    """Render a DEM to a publication-quality PNG using forge3d."""

    root = Path(__file__).parent.parent
    with open(root / 'config.yaml') as f:
        cfg = yaml.safe_load(f)

    render_cfg = cfg['render']

    # Resolve DEM path
    if dem:
        dem_path = Path(dem)
    else:
        active = site or cfg['active_site']
        dem_path = root / cfg['dem']['output_dir'] / f'{active}_dem_1m.tif'

    if not dem_path.exists():
        click.echo(f"DEM not found: {dem_path}", err=True)
        click.echo("Run notebook 02 first to generate the DEM, or pass --dem path/to/file.tif")
        sys.exit(1)

    click.echo(f"Loading DEM: {dem_path}")
    dem_arr = load_dem_as_array(dem_path)
    click.echo(f"  Shape: {dem_arr.shape}  Elevation: {dem_arr.min():.1f}–{dem_arr.max():.1f}m")

    # Output path
    renders_dir = root / render_cfg['output_dir']
    renders_dir.mkdir(parents=True, exist_ok=True)

    stem = dem_path.stem
    out_path = out or str(renders_dir / f'{stem}_render.png')

    render_dem(
        dem_arr, out_path,
        phi_deg=phi, theta_deg=theta, radius=radius,
        sun_az=render_cfg['sun_azimuth_deg'],
        sun_el=render_cfg['sun_elevation_deg'],
        width=width, height=height, samples=samples,
    )

    if panel:
        click.echo("\nRendering 4-angle panel...")
        angles = [
            (225, 35,  'se_oblique'),
            (315, 45,  'nw_oblique'),
            (180, 20,  's_low'),
            (0,   90,  'nadir'),
        ]
        panel_paths = []
        for p, t, label in angles:
            ap = str(renders_dir / f'{stem}_{label}.png')
            click.echo(f"\n  {label}")
            render_dem(dem_arr, ap, phi_deg=p, theta_deg=t, radius=1.3,
                       width=1920, height=1080, samples=32)
            panel_paths.append(ap)

        # Stitch panel with PIL
        from PIL import Image
        imgs = [Image.open(p) for p in panel_paths]
        pw, ph = imgs[0].size
        panel_img = Image.new('RGBA', (pw * 2, ph * 2))
        for i, img in enumerate(imgs):
            panel_img.paste(img, ((i % 2) * pw, (i // 2) * ph))
        panel_out = str(renders_dir / f'{stem}_panel.png')
        panel_img.save(panel_out)
        click.echo(f"\nPanel saved: {panel_out}")


if __name__ == '__main__':
    main()
