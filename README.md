# Project Kiva

<p align="center">
  <img src="data/assets/project-kiva_flag_V2.png" alt="Project Kiva" width="800"/>
</p>

<p align="center">
  <em>Archaeological LiDAR Survey — American Southwest</em>
</p>

---

**Somewhere under a bare-earth point cloud is a wall nobody has stood next to
in a thousand years. This project goes and finds it.**

No shovel, no dig permit, no helicopter — just publicly available airborne
LiDAR, a laptop, and the same technique that found lost cities under the
Guatemalan canopy and revealed the true scale of Angkor. Point a scanner at
the desert, strip away everything but the bare ground, and the earth itself
starts telling you where people built things.

Named for the **kiva** — the subterranean ceremonial chamber at the heart of
Ancestral Puebloan architecture, and precisely the kind of subtle,
low-relief feature that a LiDAR survey pulls out of the ground after a
thousand years of wind have tried to erase it.

---

## First find: Pueblo Bonito, reveal in hand

Chaco Canyon's Pueblo Bonito is one of the most excavated, most photographed
archaeological sites in North America — over 700 rooms, the center of the
Chacoan world, construction spanning 850-1150 CE. It should not be possible
to "discover" anything about it from a laptop. And yet:

![Pueblo Bonito Local Relief Model reveal](docs/images/pueblo_bonito_lrm_reveal.jpg)
*Local Relief Model, Pueblo Bonito, generated from raw LiDAR points
downloaded the same day this image was made. The D-shaped arc of room-block
cells and what are almost certainly the two great kivas in the plaza are
visible without ever opening a photograph of the site.*

Here's what actually happened, in order:

1. **The standard 1-meter DEM product has a hole exactly where Pueblo
   Bonito sits.** Queried USGS's National Map API for 1m elevation data
   over the canyon core — zero results. The finished product simply
   doesn't cover the most important square kilometer in the park.
2. **The raw LiDAR does.** A newer USGS gap-fill acquisition
   (`CO_CONMGaps_D24`, published 2026) has a point cloud tile sitting
   directly over the canyon core that never got turned into a DEM. Found
   it, downloaded it: 55 MB, one `.laz` tile, 1 km x 1 km.
3. **Built the DEM from scratch.** 14,792,731 points in the tile, 13,026,412
   of them already ground-classified (88%) — dense, clean survey data.
   Gridded the ground returns to a 1-meter bare-earth surface.
4. **Local Relief Model.** The canyon's broad slope and the coarse trend
   both drown out sub-meter archaeology, so the DEM gets differenced
   against a heavily smoothed version of itself (15 m Gaussian). What's
   left is stripped of topography and keeps only the fine relief — wall
   stubs, room depressions, midden mounds.
5. **Zoomed to the coordinates and there it was.** No enhancement, no
   guessing — the room-block arc and kiva depressions came straight out of
   a tight, zero-centered color stretch on the raw computation.

This is a **visual identification against a known, extensively excavated
site**, not a new archaeological discovery and not an automated detection —
see `feature_detection` in the roadmap below for where that's headed. It's
here because turning raw laser returns into a floor plan you can recognize,
on the same day the point cloud was downloaded, is exactly the kind of
result this project exists to produce.

---

## The canyon in three dimensions

![Chaco Canyon rendered in 3D with forge3d](docs/images/chaco_canyon_forge3d.jpg)
*The same square kilometer, rendered as terrain. Chaco Wash cuts the frame
diagonally; the cliff line at left is the canyon's south wall. Built from the
project's own bare-earth DEM with [forge3d](https://github.com/milos-agathon/forge3d),
sun at 302 deg azimuth / 24 deg elevation — no compositing, no hand-editing.*

```powershell
pixi run python scripts/render_site.py --dem data/processed/pueblo_bonito_dem_1m.tif
```

---

## Study Areas

| Site | State | Period | Key Features |
|------|-------|--------|-------------|
| **Chaco Canyon** | NM | 850-1150 CE | Great houses, road network, kivas |
| **Mesa Verde** | CO | 600-1300 CE | Cliff dwellings, mesa-top villages |
| **Hohokam Phoenix** | AZ | 300-1450 CE | Canal network, platform mounds |
| **Canyon de Chelly** | AZ | 2500 BCE-present | Cliff dwellings, petroglyphs |

Switch between sites by changing `active_site` in `config.yaml`.

---

## Quickstart

```powershell
# Install environment (Windows)
pixi install

# Download DEMs / point cloud tiles for the active site
pixi run python scripts/download_dem.py

# Ground classification -> bare-earth DEM -> Local Relief Model
pixi run python scripts/run_pipeline.py

# Render 3D terrain
pixi run python scripts/render_site.py --site chaco

# Open notebooks
pixi run notebooks
```

---

## Project Structure

```
project-kiva/
├── config.yaml                  ← Switch sites here
├── pixi.toml                    ← Python environment
│
├── notebooks/
│   ├── 01_data_acquisition      Download USGS 3DEP LiDAR tiles
│   ├── 02_render_forge3d        3D terrain renders via forge3d
│   ├── 03_lidar_processing      Point cloud -> bare-earth DEM      (roadmap)
│   ├── 04_archaeological_viz    SVF, LRM, hillshade products       (roadmap)
│   └── 05_feature_detection     Automated mound/kiva detection     (roadmap)
│
├── scripts/
│   ├── download_dem.py          Download GeoTIFF DEMs / LAZ tiles from USGS
│   ├── run_pipeline.py          Ground points -> DEM -> Local Relief Model
│   └── render_site.py           forge3d 3D terrain renderer
│
├── data/
│   ├── raw/          LAZ point cloud tiles (gitignored)
│   ├── processed/    GeoTIFFs and raster products (gitignored)
│   ├── renders/      Full-res PNG render outputs (gitignored)
│   ├── vectors/      GeoJSON site features (committed)
│   └── assets/       Project imagery and branding
│
├── docs/images/       Compressed hero images for this README (committed)
│
└── web/
    └── index.html    GitHub Pages interactive map
```

---

## Pipeline

```
USGS 3DEP tiles (LAZ point cloud / GeoTIFF DEM)
    |
Ground classification (from USGS delivery) -> bare-earth DEM, 1m
    |
+-------------------------------------------------------+
|  Archaeological visualization suite                   |
|  * Local Relief Model (LRM)     -- built, see above    |  <- wall stubs, mounds, plaza edges
|  * Multi-azimuth hillshade      -- roadmap              |
|  * Sky-View Factor (SVF)        -- roadmap              |  <- best for kiva depressions, road berms
+-------------------------------------------------------+
    |
Automated detection -> candidate_features.geojson   (roadmap)
    |
forge3d path_tracing -> 3D terrain renders
    |
Leaflet web map -> GitHub Pages
```

---

## forge3d Rendering

Project Kiva uses [forge3d](https://github.com/milos-agathon/forge3d) for
GPU-accelerated 3D terrain visualization via its headless path tracer — no
Rust toolchain or viewer binary required.

```python
from forge3d import path_tracing
from forge3d._png import save_png

tracer = path_tracing.create_path_tracer(1920, 1080, max_bounces=2)
camera = path_tracing.make_camera(
    origin=(ox, oy, oz), look_at=(cx, cy, cz),
    up=(0, 0, 1), fov_y=45.0, aspect=16/9, exposure=1.0
)
rgba = tracer.render_rgba(dem_array, camera)
save_png('render.png', rgba)
```

---

## Web Map

Live at **[bdgroves.github.io/project-kiva](https://bdgroves.github.io/project-kiva)**

- Satellite, topo, and terrain basemap toggle
- Known great house and kiva locations with historical notes
- Automated candidate feature detections (roadmap)
- Schematic road and canal overlays

---

## References

- Lekson, S.H. (1999). *The Chaco Meridian.* AltaMira Press.
- Chase, A. et al. (2011). Airborne LiDAR, archaeology, and the ancient Maya landscape. *Journal of Archaeological Science*, 38(2).
- Evans, D. et al. (2013). Uncovering archaeological landscapes at Angkor using LiDAR. *PNAS*, 110(31).
- Opitz, R. & Cowley, D. (Eds.) (2013). *Interpreting Archaeological Topography.* Oxbow Books.

---

<p align="center">
  Code: MIT &nbsp;&middot;&nbsp; Data: USGS 3DEP public domain &nbsp;&middot;&nbsp; Built in Tacoma, WA
</p>

<p align="center">
  <em>Visual identifications and feature detections in this project are exploratory outputs
  against a known, well-documented site, not verified excavation-grade archaeological findings.</em>
</p>
