"""
scripts/render_site.py

3D terrain render of any processed DEM using forge3d's viewer + snapshot API.

Note: an earlier version of this script called
`path_tracing.PathTracer.render_rgba(dem, camera)`, which is not a supported
overload -- that API takes explicit scene primitives, not a DEM array, so it
silently rendered an empty scene. The viewer/snapshot path below is the
documented terrain workflow.

Usage:
    pixi run python scripts/render_site.py
    pixi run python scripts/render_site.py --dem data/processed/pueblo_bonito_dem_1m.tif
    pixi run python scripts/render_site.py --z-scale 2.0 --theta 49 --radius 700
"""

import sys
from pathlib import Path

import click
import yaml

import forge3d as f3d

ROOT = Path(__file__).parent.parent


@click.command()
@click.option("--site", default=None, help="Site key from config.yaml")
@click.option("--dem", default=None, help="Path to DEM GeoTIFF")
@click.option("--out", default=None, help="Output PNG path")
@click.option("--width", default=1920, show_default=True)
@click.option("--height", default=1080, show_default=True)
@click.option("--z-scale", default=1.5, show_default=True,
              help="Vertical exaggeration. Large values can break auto-framing.")
@click.option("--phi", default=225.0, show_default=True, help="Camera azimuth (deg)")
@click.option("--theta", default=45.0, show_default=True, help="Camera elevation (deg)")
@click.option("--radius", default=700.0, show_default=True,
              help="Camera distance, in the DEM's own coordinate units")
@click.option("--fov", default=42.0, show_default=True)
@click.option("--sun-azimuth", default=302.0, show_default=True)
@click.option("--sun-elevation", default=24.0, show_default=True)
def main(site, dem, out, width, height, z_scale, phi, theta, radius, fov,
         sun_azimuth, sun_elevation):
    """Render a DEM to PNG using forge3d's terrain viewer."""

    with open(ROOT / "config.yaml") as f:
        cfg = yaml.safe_load(f)

    active = site or cfg["active_site"]

    if dem:
        dem_path = Path(dem)
    else:
        dem_dir = ROOT / cfg["dem"]["output_dir"]
        tifs = sorted(dem_dir.glob(f"{active}_*.tif"))
        if not tifs:
            click.echo(f"No DEMs found for site '{active}' in {dem_dir}", err=True)
            click.echo("Run: pixi run python scripts/download_dem.py")
            sys.exit(1)
        dem_path = tifs[-1]
        click.echo(f"Auto-selected: {dem_path.name}")

    if not dem_path.exists():
        click.echo(f"DEM not found: {dem_path}", err=True)
        sys.exit(1)

    renders_dir = ROOT / cfg["render"]["output_dir"]
    renders_dir.mkdir(parents=True, exist_ok=True)
    out_path = out or str(renders_dir / f"{dem_path.stem}_render.png")

    click.echo(f"Rendering {dem_path.name} -> {out_path}")
    click.echo(f"  camera: phi={phi} theta={theta} radius={radius} fov={fov}")
    click.echo(f"  sun:    azimuth={sun_azimuth} elevation={sun_elevation}")
    click.echo(f"  z_scale={z_scale}")

    with f3d.open_viewer_async(terrain_path=str(dem_path),
                                width=1440, height=900) as viewer:
        viewer.set_z_scale(z_scale)
        viewer.set_orbit_camera(phi_deg=phi, theta_deg=theta,
                                 radius=radius, fov_deg=fov)
        viewer.set_sun(azimuth_deg=sun_azimuth, elevation_deg=sun_elevation)
        viewer.snapshot(out_path, width=width, height=height)

    click.echo(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
