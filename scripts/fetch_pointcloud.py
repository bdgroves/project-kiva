"""
scripts/fetch_pointcloud.py

Stream a window of USGS 3DEP point cloud straight out of AWS and rasterise it,
without downloading the project.

The whole 3DEP archive (75 trillion points, 350 TB) is published as Entwine
Point Tiles in a public, no-auth bucket. PDAL's readers.ept walks the octree
and pulls only the nodes intersecting your bounds -- the same
range-request idea as a COG, applied to points instead of pixels.

Pierce County 2020 runs about 12 pts/m2 project-wide and 15+ locally, roughly
double the QL1 spec, which supports a 0.5 m bare-earth grid where the usual
3DEP DEM gives you 1 m.

    pixi run python scripts/fetch_pointcloud.py --name fort_steilacoom \
        --west -122.5680 --east -122.5520 --south 47.1720 --north 47.1830
"""
import json
from pathlib import Path

import click
import pdal
from pyproj import Transformer

ROOT = Path(__file__).parent.parent
EPT = ("https://s3-us-west-2.amazonaws.com/usgs-lidar-public/"
       "{project}/ept.json")


@click.command()
@click.option("--name", required=True, help="Output basename")
@click.option("--project", default="WA_PierceCounty_1_2020", show_default=True,
              help="3DEP project name in the usgs-lidar-public bucket")
@click.option("--west", type=float, required=True)
@click.option("--east", type=float, required=True)
@click.option("--south", type=float, required=True)
@click.option("--north", type=float, required=True)
@click.option("--epsg", default=6339, show_default=True,
              help="Target projected CRS (6339 = NAD83(2011) UTM 10N)")
@click.option("--resolution", default=0.5, show_default=True, help="Grid size, m")
@click.option("--out-dir", default="data/processed", show_default=True)
def main(name, project, west, east, south, north, epsg, resolution, out_dir):
    """Pull an EPT window and write bare-earth DTM + first-return DSM."""
    outd = ROOT / out_dir
    outd.mkdir(parents=True, exist_ok=True)

    # EPT bounds must be given in the octree's own CRS, which is web mercator
    t = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x0, y0 = t.transform(west, south)
    x1, y1 = t.transform(east, north)
    bounds = f"([{x0},{x1}],[{y0},{y1}])"
    click.echo(f"{project}\n  bbox(3857) {bounds}")

    laz = outd / f"{name}.laz"
    dtm = outd / f"{name}_dtm_{resolution:g}m.tif"
    dsm = outd / f"{name}_dsm_{resolution:g}m.tif"

    pipeline = {
        "pipeline": [
            {"type": "readers.ept",
             "filename": EPT.format(project=project),
             "bounds": bounds},
            # 7 = low/high noise in ASPRS classes; drop before gridding
            {"type": "filters.range", "limits": "Classification![7:7]"},
            {"type": "filters.reprojection", "out_srs": f"EPSG:{epsg}"},
            {"type": "writers.las", "filename": str(laz), "compression": "laszip"},
            # bare earth: ground returns only, min Z per cell
            {"type": "filters.range", "limits": "Classification[2:2]",
             "tag": "ground"},
            {"type": "writers.gdal", "filename": str(dtm),
             "resolution": resolution, "output_type": "idw",
             "window_size": 8, "nodata": -9999},
        ]
    }
    click.echo("  streaming + gridding bare earth...")
    p = pdal.Pipeline(json.dumps(pipeline))
    n = p.execute()
    click.echo(f"  {n:,} points")

    # first returns -> surface model (canopy + rooftops)
    surf = {
        "pipeline": [
            {"type": "readers.las", "filename": str(laz)},
            {"type": "filters.range", "limits": "ReturnNumber[1:1]"},
            {"type": "writers.gdal", "filename": str(dsm),
             "resolution": resolution, "output_type": "max",
             "window_size": 8, "nodata": -9999},
        ]
    }
    click.echo("  gridding surface...")
    pdal.Pipeline(json.dumps(surf)).execute()

    click.echo(f"\nwrote:\n  {laz}\n  {dtm}\n  {dsm}")


if __name__ == "__main__":
    main()
