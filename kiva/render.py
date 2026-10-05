"""
forge3d renders of a site: the bare-earth block as a museum specimen.

The DTM is meshed by forge3d's terrain viewer, the relief composite (or the
NAIP photograph, for comparison) is draped over it as a texture, and the
viewer lights it with PBR shading, shadows and ambient occlusion from a low,
raking sun, the light archaeologists wait for. Runs headless on a CPU (Mesa
llvmpipe under Xvfb) or on a GPU.

Viewer world coordinates (from the forge3d source): x = easting,
y = (elevation - DEM minimum) * zscale, z = -northing.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy.ndimage import gaussian_filter

Image.MAX_IMAGE_PIXELS = None
FONTS = Path(__file__).resolve().parent / "fonts"
MAX_GRID = 2048          # the viewer meshes at most this many vertices across
MAX_TEX = 8192
MAX_THETA = 85.0

# grey relief -> umber..bone, so the block reads as earth, not as a printout
EARTH = [(0.00, (28, 21, 16)), (0.25, (82, 60, 42)), (0.50, (146, 114, 82)),
         (0.75, (205, 182, 148)), (1.00, (246, 238, 222))]
BG_TOP, BG_BOTTOM = np.array([30, 26, 22]), np.array([10, 9, 8])


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def ramp(t, stops):
    out = np.zeros(t.shape + (3,), np.float32)
    for (v0, c0), (v1, c1) in zip(stops[:-1], stops[1:]):
        m = (t >= v0) & (t <= v1)
        w = ((t - v0) / (v1 - v0))[m][:, None]
        out[m] = np.array(c0) * (1 - w) + np.array(c1) * w
    return out


# ── scene preparation ────────────────────────────────────────────────────────
def prepare(site_dir: Path, products: dict, dtm_filled, prof, photo=None):
    """Write the render DEM and textures next to the site's other outputs."""
    work = site_dir / "render"
    work.mkdir(parents=True, exist_ok=True)
    H, W = dtm_filled.shape
    k = max(1.0, max(H, W) / MAX_GRID)
    dem = dtm_filled
    if k > 1:
        from rasterio.warp import Resampling, reproject
        h2, w2 = int(round(H / k)), int(round(W / k))
        t2 = prof["transform"] * prof["transform"].scale(W / w2, H / h2)
        dem = np.zeros((h2, w2), np.float32)
        reproject(dtm_filled, dem, src_transform=prof["transform"], src_crs=prof["crs"],
                  dst_transform=t2, dst_crs=prof["crs"], resampling=Resampling.average)
        p2 = dict(prof, height=h2, width=w2, transform=t2)
    else:
        p2 = dict(prof)
    dem = gaussian_filter(dem, 0.6).astype(np.float32)
    p2.update(count=1, dtype="float32", nodata=None, driver="GTiff")
    with rasterio.open(work / "dem.tif", "w", **p2) as d:
        d.write(dem, 1)

    def tex(rgb, name):
        im = Image.fromarray(rgb)
        s = MAX_TEX / max(im.size)
        if s < 1:
            im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        im.save(work / name)

    comp = products["composite"]
    lo, hi = np.nanpercentile(comp, [1.5, 99.5])
    t = 0.10 + 0.80 * np.clip((np.nan_to_num(comp, nan=float(np.nanmedian(comp))) - lo) / (hi - lo), 0, 1)
    tex(ramp(t, EARTH).astype(np.uint8), "relief.png")
    if photo is not None:
        tex(photo, "photo.png")
    return work


class Block:
    def __init__(self, work: Path, site: dict):
        with rasterio.open(work / "dem.tif") as s:
            self.dem = s.read(1)
            self.T = s.transform
            self.B = s.bounds
            self.crs = s.crs
        self.work = work
        self.site = site
        self.zs = float(site.get("zscale", 2.0))
        self.min_h = float(self.dem.min())
        self.cx = (self.B.left + self.B.right) / 2
        self.cy = (self.B.bottom + self.B.top) / 2
        self.half = 0.5 * math.hypot(self.B.right - self.B.left, self.B.top - self.B.bottom)
        self.target = self.world(self.cx, self.cy, float(np.median(self.dem)))
        # coarse surface for the silhouette mask
        n = 120
        rr = np.linspace(0, self.dem.shape[0] - 1, n).astype(int)
        cc = np.linspace(0, self.dem.shape[1] - 1, n).astype(int)
        xs = self.B.left + (cc + 0.5) * self.T.a
        ys = self.B.top + (rr + 0.5) * self.T.e
        X, Y = np.meshgrid(xs, ys)
        Z = self.dem[np.ix_(rr, cc)]
        self.surf = np.stack([X, (Z - self.min_h) * self.zs, -Y], axis=-1)

    def world(self, x, y, h):
        return np.array([x, (h - self.min_h) * self.zs, -y], float)

    def ground(self, x, y):
        r, c = rasterio.transform.rowcol(self.T, x, y)
        r = min(max(r, 0), self.dem.shape[0] - 1)
        c = min(max(c, 0), self.dem.shape[1] - 1)
        return float(self.dem[r, c])

    def feature_world(self, f):
        from pyproj import Transformer
        x, y = Transformer.from_crs("EPSG:4326", self.crs, always_xy=True).transform(f["lon"], f["lat"])
        return self.world(x, y, self.ground(x, y))

    def eye(self, phi_deg, elev_deg, size, vfov):
        aspect = size[0] / size[1]
        hf = math.degrees(2 * math.atan(math.tan(math.radians(vfov) / 2) * aspect))
        relief = (float(self.dem.max()) - self.min_h) * self.zs
        r = 1.25 * max(self.half / math.tan(math.radians(hf) / 2),
                       (self.half * math.sin(math.radians(elev_deg)) + relief) / math.tan(math.radians(vfov) / 2))
        r *= float(self.site.get("camera_zoom", 1.0))
        e, p = math.radians(elev_deg), math.radians(phi_deg)
        # phi: compass direction FROM the target TO the camera
        off = np.array([r * math.cos(e) * math.sin(p), r * math.sin(e), -r * math.cos(e) * math.cos(p)])
        return self.target + off


def camera_cmd(eye, aim, fov):
    off = eye - aim
    r = float(np.linalg.norm(off))
    return {"cmd": "set_terrain_camera", "phi_deg": math.degrees(math.atan2(off[2], off[0])),
            "theta_deg": min(MAX_THETA, math.degrees(math.acos(off[1] / r))), "radius": r,
            "fov_deg": fov, "target": [float(v) for v in aim]}


def project(P, eye, aim, fov, size):
    """World points (..., 3) -> screen x, y and depth (same leading shape)."""
    f = aim - eye
    f /= np.linalg.norm(f)
    r = np.cross(f, [0.0, 1.0, 0.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    d = P - eye
    z = d @ f
    th = math.tan(math.radians(fov) / 2)
    x = (d @ r) / (np.maximum(z, 1e-6) * th * size[0] / size[1])
    y = (d @ u) / (np.maximum(z, 1e-6) * th)
    return (x + 1) / 2 * size[0], (1 - y) / 2 * size[1], z


def silhouette(block: Block, eye, aim, fov, size, ss=2):
    """Where the block is on screen, drawn from the projected surface."""
    W, H = size[0] * ss, size[1] * ss
    x, y, _ = project(block.surf, eye, aim, fov, size)
    x, y = x * ss, y * ss
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    n0, n1 = x.shape
    for i in range(n0 - 1):
        for j in range(n1 - 1):
            d.polygon([(x[i, j], y[i, j]), (x[i, j + 1], y[i, j + 1]),
                       (x[i + 1, j + 1], y[i + 1, j + 1]), (x[i + 1, j], y[i + 1, j])], fill=255)
    im = im.filter(ImageFilter.MaxFilter(3)).resize(size, Image.LANCZOS)
    return np.asarray(im, np.float32) / 255


def backdrop(size):
    W, H = size
    t = np.linspace(0, 1, H)[:, None, None]
    g = BG_TOP * (1 - t) + BG_BOTTOM * t
    yy, xx = np.mgrid[0:H, 0:W]
    v = 1 - 0.35 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H * 0.45) / (H * 0.8)) ** 2)
    return np.broadcast_to(g, (H, W, 3)) * np.clip(v, 0.55, 1)[..., None]


def finish(png: Path, mask: np.ndarray, shadow_off=(0.0, 0.02)) -> Image.Image:
    img = np.asarray(Image.open(png).convert("RGB")).astype(np.float32)
    H, W = mask.shape
    bg = backdrop((W, H)).copy()
    # a soft contact shadow under the block
    sh = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(W / 90)), np.float32) / 255
    k = int(shadow_off[1] * H)
    sh = np.vstack([np.zeros((k, W), np.float32), sh[:H - k]]) if k > 0 else sh
    bg *= (1 - 0.55 * sh)[..., None]
    img = np.clip((img - 128) * 1.06 + 128, 0, 255)
    out = img * mask[..., None] + bg * (1 - mask[..., None])
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8))


def label(im, xy, text, sub=None, alpha=1.0):
    if xy is None or alpha <= 0.01:
        return
    x, y = xy
    W, H = im.size
    if not (0 < x < W and 0 < y < H):
        return
    s = W / 1920
    edge = min(x, W - x) / (0.05 * W), (H - y) / (0.07 * H)
    alpha *= max(0.0, min(1.0, *edge))
    if alpha <= 0.01:
        return
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = int(255 * alpha)
    stem = 52 * s
    d.line([(x, y), (x, y - stem)], fill=(255, 244, 220, a), width=max(1, int(2 * s)))
    d.ellipse([x - 4 * s, y - 4 * s, x + 4 * s, y + 4 * s], fill=(255, 220, 160, a))
    f1 = font("cinzel-latin-600-normal.woff", int(28 * s))
    f2 = font("crimson-text-latin-400-italic.woff", int(21 * s))
    tx, ty = x + 10 * s, y - stem - 28 * s
    tw = max(d.textlength(text, font=f1), d.textlength(sub, font=f2) if sub else 0)
    if tx + tw > W - 12 * s:
        tx = x - 10 * s - tw
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
        d.text((tx + dx * s, ty + dy * s), text, font=f1, fill=(15, 10, 6, int(a * 0.6)))
    d.text((tx, ty), text, font=f1, fill=(255, 246, 228, a))
    if sub:
        d.text((tx + 1, ty + 32 * s), sub, font=f2, fill=(15, 10, 6, int(a * 0.5)))
        d.text((tx, ty + 31 * s), sub, font=f2, fill=(250, 232, 200, a))
    im.paste(Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB"))


def caption(im, title, sub=None):
    W, H = im.size
    s = W / 1920
    d = ImageDraw.Draw(im)
    d.text((64 * s, H - 118 * s), title, font=font("cinzel-latin-400-normal.woff", int(40 * s)),
           fill=(240, 214, 160))
    if sub:
        d.text((66 * s, H - 64 * s), sub, font=font("courier-prime-latin-400-normal.woff", int(19 * s)),
               fill=(196, 178, 150))


def pins(im, block, eye, aim, fov, size, features, alpha=1.0):
    for f in features:
        if not f.get("pin", True):
            continue
        x, y, z = project(block.feature_world(f), eye, aim, fov, size)
        if z > 1:
            label(im, (float(x), float(y)), f["name"], f.get("short"), alpha)


# ── viewer ───────────────────────────────────────────────────────────────────
class Viewer:
    def __init__(self, block: Block, texture: str, size, fov):
        from forge3d.viewer import open_viewer_async
        self.size = size
        self.v = open_viewer_async(width=size[0], height=size[1], terrain_path=str(block.work / "dem.tif"),
                                   fov_deg=fov, timeout=600)
        self.v.load_overlay("tex", str(block.work / texture), extent=(0.0, 0.0, 1.0, 1.0), z_order=0)
        self.v.send_ipc({"cmd": "set_terrain_pbr", "enabled": True, "exposure": 0.55,
                         "shadow_map_res": 4096,
                         "height_ao": {"enabled": True, "strength": 0.9, "max_distance": 60.0},
                         "sun_visibility": {"enabled": True, "mode": "soft", "max_distance": 1500.0}})
        self.v.send_ipc({"cmd": "set_terrain", "ambient": 0.10, "zscale": block.zs})
        site = block.site
        self.v.send_ipc({"cmd": "set_terrain_sun", "azimuth_deg": float(site.get("sun_az", 315)),
                         "elevation_deg": float(site.get("sun_el", 22)), "intensity": 1.0})

    def shot(self, eye, aim, fov, path):
        self.v.send_ipc(camera_cmd(eye, aim, fov))
        self.v.snapshot(str(path), *self.size)

    def close(self):
        self.v.close()


ELEV = 36.0
FOV = 32.0


def stills(block: Block, out: Path, size=(1920, 1080), credit=""):
    """Relief and photograph from the same camera, labelled."""
    out.mkdir(parents=True, exist_ok=True)
    site = block.site
    phi = float(site.get("view_az", 200))
    eye = block.eye(phi, ELEV, size, FOV)
    mask = silhouette(block, eye, block.target, FOV, size)
    made = []
    for tex, name, title in (("relief.png", "relief", "bare earth"),
                             ("photo.png", "photo", "from the air")):
        if not (block.work / tex).exists():
            continue
        v = Viewer(block, tex, size, FOV)
        raw = out / f"_{name}_raw.png"
        v.shot(eye, block.target, FOV, raw)
        v.close()
        im = finish(raw, mask)
        pins(im, block, eye, block.target, FOV, size, site.get("features", []))
        caption(im, f"{site['name']} · {title}", credit if name == "relief" else site.get("photo_credit", ""))
        im.save(out / f"{name}.jpg", quality=90)
        raw.unlink()
        made.append(name)
    return made


def orbit(block: Block, frames_dir: Path, chunk=0, chunks=1, seconds=14.0, fps=30, size=(1280, 720)):
    """One slow turn around the block; frames are split across parallel jobs."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    n = int(seconds * fps)
    mine = [i for i in range(n) if i * chunks // n == chunk]
    site = block.site
    phi0 = float(site.get("view_az", 200))
    v = Viewer(block, "relief.png", size, FOV)
    try:
        for i in mine:
            t = i / n
            phi = phi0 + 360.0 * t
            elev = ELEV + 6.0 * math.sin(2 * math.pi * t)
            eye = block.eye(phi, elev, size, FOV)
            raw = frames_dir / f"_raw_{i:04d}.png"
            v.shot(eye, block.target, FOV, raw)
            im = finish(raw, silhouette(block, eye, block.target, FOV, size))
            pins(im, block, eye, block.target, FOV, size, site.get("features", []))
            im.save(frames_dir / f"frame_{i:04d}.jpg", quality=92)
            raw.unlink()
            print(f"  frame {i + 1}/{n}", flush=True)
    finally:
        v.close()


def encode(frames_dir: Path, out_mp4: Path, fps=30):
    ff = shutil.which("ffmpeg") or "ffmpeg"
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(fps),
                    "-i", str(frames_dir / "frame_%04d.jpg"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "24", "-preset", "slow", "-movflags", "+faststart", str(out_mp4)], check=True)
    frames = sorted(frames_dir.glob("frame_*.jpg"))
    if frames:
        Image.open(frames[0]).save(out_mp4.with_suffix(".jpg"), quality=86)
