"""
Project Kiva command line.

    pixi run kiva sites                 # list the catalog
    pixi run kiva build cahokia         # lidar -> DTM -> relief -> web layers
    pixi run kiva photo cahokia         # NAIP for the "from the air" render
    pixi run kiva render cahokia        # forge3d stills + orbit video
    pixi run kiva all cahokia           # all of the above
    pixi run kiva index                 # sites.json from every built site
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import click
import numpy as np
import rasterio
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "sites"
WEB = ROOT / "sites"


def catalog():
    return yaml.safe_load((ROOT / "sites.yaml").read_text(encoding="utf-8"))["sites"]


def get_site(sid):
    cat = catalog()
    if sid not in cat:
        raise click.BadParameter(f"unknown site {sid!r}; try: {', '.join(cat)}")
    return dict(cat[sid], id=sid)


def tif_write(path, arr, prof):
    p = {k: v for k, v in prof.items() if k not in ("blockxsize", "blockysize", "tiled", "interleave")}
    p.update(count=1, dtype="float32", nodata=np.nan, compress="deflate", predictor=3,
             tiled=True, blockxsize=256, blockysize=256, driver="GTiff")
    with rasterio.open(path, "w", **p) as d:
        d.write(arr.astype("float32"), 1)


def highest(dtm, prof, res, n=3, sep_m=80.0):
    """The n highest points at least sep_m apart, as [lat, lon, elevation].
    A cheap check on the pins: Monks Mound should find itself."""
    from pyproj import Transformer
    from scipy.ndimage import maximum_filter
    z = np.where(np.isfinite(dtm), dtm, -1e9)
    k = max(3, int(sep_m / res) | 1)
    peak = (z == maximum_filter(z, size=k)) & np.isfinite(dtm)
    rr, cc = np.nonzero(peak)
    order = np.argsort(z[rr, cc])[::-1][:n]
    t = Transformer.from_crs(prof["crs"], "EPSG:4326", always_xy=True)
    out = []
    for i in order:
        x, y = rasterio.transform.xy(prof["transform"], int(rr[i]), int(cc[i]))
        lon, lat = t.transform(x, y)
        out.append([round(lat, 6), round(lon, 6), round(float(z[rr[i], cc[i]]), 1)])
    return out


@click.group()
def main():
    """Project Kiva: reading the ground with lasers."""


@main.command()
def sites():
    for sid, s in catalog().items():
        built = (WEB / sid / "site.json").exists()
        click.echo(f"{'*' if built else ' '} {sid:16s} {s['name']:20s} {s['source']:8s} {s['res']} m  {s['place']}")


@main.command()
@click.argument("sid")
@click.option("--refetch", is_flag=True, help="Fetch points again even if the DTM exists")
def build(sid, refetch):
    """Points -> bare-earth DTM -> relief products -> web layers."""
    from kiva import fetch, relief, web
    site = get_site(sid)
    work, out = WORK / sid, WEB / sid
    work.mkdir(parents=True, exist_ok=True)
    raw = work / "dtm_raw.tif"
    prov_path = work / "provenance.json"
    t0 = time.time()
    click.echo(f"{site['name']}: {site['source']} {site.get('project', '')}")
    if refetch or not raw.exists():
        if site["source"] == "ept":
            prov = fetch.fetch_ept(site, raw, log=click.echo)
        else:
            prov = fetch.fetch_tnm(site, raw, work / "laz", log=click.echo)
        prov_path.write_text(json.dumps(prov))
    prov = json.loads(prov_path.read_text())
    dtm, prof = fetch.read_dtm(raw)
    tif_write(work / "dtm.tif", dtm, prof)
    cover = float(np.isfinite(dtm).mean())
    click.echo(f"  DTM {dtm.shape[1]} x {dtm.shape[0]} at {site['res']} m, {cover:.1%} with ground returns")

    click.echo("  relief products...")
    prods = relief.all_products(dtm, site["res"])
    (work / "products").mkdir(exist_ok=True)
    for k, v in prods.items():
        tif_write(work / "products" / f"{k}.tif", v, prof)
    meta = web.export(prods, prof, out)

    peaks = highest(dtm, prof, site["res"])
    area = dtm.size * site["res"] ** 2
    zf = dtm[np.isfinite(dtm)]
    info = {
        "id": sid, "name": site["name"], "place": site["place"], "region": site.get("region"),
        "blurb": " ".join(site.get("blurb", "").split()),
        "center": site["center"], "res_m": site["res"], "crs": site["crs"],
        "size_m": site["size_m"], "source": prov["source"], "project": prov["project"],
        "ground_points": prov["ground_points"],
        "ground_density": round(prov["ground_points"] / area, 2),
        "coverage": round(cover, 4),
        "elev_m": [round(float(zf.min()), 1), round(float(zf.max()), 1)],
        "features": site.get("features", []),
        "highest": peaks,
        **meta,
    }
    web.write_json(info, out / "site.json")
    click.echo(f"  done in {time.time() - t0:.0f} s -> {out.relative_to(ROOT)}")


@main.command()
@click.argument("sid")
def photo(sid):
    """NAIP aerial photo on the DTM grid (for the comparison render)."""
    from kiva.imagery import naip
    site = get_site(sid)
    work = WORK / sid
    with rasterio.open(work / "dtm.tif") as s:
        T, shape = s.transform, s.shape
    rgb, year = naip(site, T, shape, log=click.echo)
    if rgb is None:
        click.echo("  no NAIP here")
        return
    np.save(work / "naip.npy", rgb)
    info_p = WEB / sid / "site.json"
    info = json.loads(info_p.read_text())
    info["photo"] = {"source": "USDA NAIP", "year": year}
    info_p.write_text(json.dumps(info, indent=1, ensure_ascii=False))


def _block(sid):
    from kiva import render
    site = get_site(sid)
    work = WORK / sid
    with rasterio.open(work / "dtm.tif") as s:
        dtm, prof = s.read(1), s.profile
    from kiva.relief import fill_nodata
    filled, _ = fill_nodata(dtm)
    with rasterio.open(work / "products" / "composite.tif") as s:
        comp = s.read(1)
    naip_p = work / "naip.npy"
    photo = np.load(naip_p) if naip_p.exists() else None
    rdir = render.prepare(work, {"composite": comp}, filled, prof, photo)
    return render.Block(rdir, site), site


def _credit(sid):
    info = json.loads((WEB / sid / "site.json").read_text())
    return f"bare-earth lidar · {info['res_m']:g} m · {info['project']} · forge3d"


@main.command()
@click.argument("sid")
@click.option("--width", default=1920)
def stills(sid, width):
    """forge3d stills: the relief block and the photo block, same camera."""
    from kiva import render
    block, site = _block(sid)
    size = (width, width * 9 // 16)
    made = render.stills(block, WEB / sid, size, credit=_credit(sid))
    info_p = WEB / sid / "site.json"
    info = json.loads(info_p.read_text())
    info["stills"] = [f"{m}.jpg" for m in made]
    info_p.write_text(json.dumps(info, indent=1, ensure_ascii=False))


@main.command()
@click.argument("sid")
@click.option("--chunk", default=0)
@click.option("--chunks", default=1)
@click.option("--seconds", default=14.0)
@click.option("--width", default=1280)
def orbit(sid, chunk, chunks, seconds, width):
    """Orbit frames (split across parallel jobs with --chunk/--chunks)."""
    from kiva import render
    block, _ = _block(sid)
    render.orbit(block, WORK / sid / "frames", chunk, chunks, seconds, size=(width, width * 9 // 16))


@main.command()
@click.argument("sid")
@click.option("--frames", default=None, help="Frames folder (default data/sites/<id>/frames)")
def encode(sid, frames):
    from kiva import render
    fdir = Path(frames) if frames else WORK / sid / "frames"
    render.encode(fdir, WEB / sid / "orbit.mp4")
    info_p = WEB / sid / "site.json"
    info = json.loads(info_p.read_text())
    info["video"] = "orbit.mp4"
    info["poster"] = "orbit.jpg"
    info_p.write_text(json.dumps(info, indent=1, ensure_ascii=False))


@main.command(name="all")
@click.argument("sid")
@click.pass_context
def all_(ctx, sid):
    ctx.invoke(build, sid=sid)
    ctx.invoke(photo, sid=sid)
    ctx.invoke(stills, sid=sid)
    ctx.invoke(orbit, sid=sid)
    ctx.invoke(encode, sid=sid)


@main.command()
def index():
    """Gather every built site into sites.json for the atlas."""
    import runpy
    runpy.run_path(str(ROOT / "scripts" / "site_index.py"))


if __name__ == "__main__":
    main()
