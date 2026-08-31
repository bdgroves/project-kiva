"""
scripts/flythrough.py

Render an orbiting flythrough of a DEM with forge3d, then grade the frames and
mux to MP4.

Full pipeline:
    pixi run python scripts/flythrough.py --dem data/processed/artillery_hill.tif
    pixi run python scripts/postprocess_frames.py
    pixi run ffmpeg -y -framerate 24 -i data/renders/frames_final/frame_%04d.png \
        -c:v libx264 -pix_fmt yuv420p -crf 18 data/renders/out.mp4

Camera notes learned the hard way:
  * phi/theta/radius orbit works reliably; passing an explicit `target` in
    projected coordinates trips the viewer's internal coordinate rebasing.
  * Keep z_scale moderate (2-3). Large values inflate the vertical bounding
    box and the auto-framing puts the terrain off-screen.
  * radius is in the DEM's own units, roughly 0.7-1.4x the tile width.
"""
from pathlib import Path
import shutil

import click
import forge3d as f3d

ROOT = Path(__file__).parent.parent


@click.command()
@click.option("--dem", required=True, help="Path to DEM GeoTIFF")
@click.option("--out-dir", default="data/renders/frames_raw", show_default=True)
@click.option("--fps", default=24, show_default=True)
@click.option("--width", default=1280, show_default=True)
@click.option("--height", default=720, show_default=True)
@click.option("--z-scale", default=3.0, show_default=True)
@click.option("--sun-azimuth", default=315.0, show_default=True)
@click.option("--sun-elevation", default=22.0, show_default=True)
@click.option("--radius-wide", default=1500.0, show_default=True,
              help="Camera distance at the high/wide keyframes")
@click.option("--radius-close", default=720.0, show_default=True,
              help="Camera distance at the low/close keyframe")
@click.option("--duration", default=10.0, show_default=True, help="Seconds")
def main(dem, out_dir, fps, width, height, z_scale, sun_azimuth,
         sun_elevation, radius_wide, radius_close, duration):
    """Orbit a DEM once, swooping in low at the midpoint, and loop seamlessly."""
    dem_path = ROOT / dem if not Path(dem).is_absolute() else Path(dem)
    if not dem_path.exists():
        raise SystemExit(f"DEM not found: {dem_path}")

    out = ROOT / out_dir
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    mid = radius_wide - (radius_wide - radius_close) * 0.55

    # phi runs 20 -> 380 so the last frame matches the first: seamless loop.
    anim = f3d.CameraAnimation()
    anim.add_keyframe(time=0.0,             phi=20,  theta=55, radius=radius_wide,  fov=45)
    anim.add_keyframe(time=duration * 0.25, phi=110, theta=38, radius=mid,          fov=45)
    anim.add_keyframe(time=duration * 0.50, phi=200, theta=26, radius=radius_close, fov=48)
    anim.add_keyframe(time=duration * 0.75, phi=290, theta=34, radius=mid,          fov=45)
    anim.add_keyframe(time=duration,        phi=380, theta=55, radius=radius_wide,  fov=45)

    def progress(i, n):
        if i % 40 == 0:
            click.echo(f"  frame {i}/{n}")

    click.echo(f"Rendering {dem_path.name}: {duration}s @ {fps}fps -> {out}")
    with f3d.open_viewer_async(terrain_path=str(dem_path),
                                width=width, height=height) as viewer:
        viewer.set_z_scale(z_scale)
        viewer.set_sun(azimuth_deg=sun_azimuth, elevation_deg=sun_elevation)
        viewer.render_animation(anim, str(out), fps=fps,
                                 width=width, height=height,
                                 progress_callback=progress)

    click.echo(f"Done. Next: pixi run python scripts/postprocess_frames.py")


if __name__ == "__main__":
    main()
