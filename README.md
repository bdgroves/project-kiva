# 🏺 Project Kiva

**Archaeological LiDAR Survey — American Southwest**

A reproducible remote sensing pipeline for detecting and visualizing archaeological features across the ancient Southwest — Chaco Canyon, Mesa Verde, the Hohokam canal network, Canyon de Chelly, and beyond.

Named for the **kiva** — the subterranean ceremonial chamber at the heart of Ancestral Puebloan architecture, and the kind of subtle feature LiDAR reveals that centuries of desert wind have hidden from the surface.

---

<!-- Replace with your actual forge3d render after running notebook 02 -->
> 📸 **Hero image:** Run `pixi run render` after downloading a DEM to generate your own render here.

---

## Study Areas

| Site | State | Period | Key Features |
|------|-------|--------|-------------|
| **Chaco Canyon** | NM | 850–1150 CE | Great houses, road network, kivas |
| **Mesa Verde** | CO | 600–1300 CE | Cliff dwellings, mesa-top villages |
| **Hohokam Phoenix** | AZ | 300–1450 CE | Canal network, platform mounds |
| **Canyon de Chelly** | AZ | 2500 BCE–present | Cliff dwellings, petroglyphs |

Switch sites by editing `active_site` in `config.yaml`.

---

## Quickstart

```powershell
# 1. Install pixi if needed
curl -fsSL https://pixi.sh/install.sh | bash   # or: iwr -useb https://pixi.sh/install.ps1 | iex

# 2. Install environment
cd project-kiva
pixi install

# 3. Open notebooks
pixi run notebooks

# 4. Or render directly from CLI (after downloading a DEM)
pixi run render --site chaco --samples 64 --panel
```

---

## Project Structure

```
project-kiva/
├── config.yaml              ← Switch sites here
├── pixi.toml                ← Python environment (Windows)
│
├── notebooks/
│   ├── 01_data_acquisition.ipynb    Download USGS 3DEP LiDAR tiles
│   ├── 02_render_forge3d.ipynb      3D terrain renders via forge3d
│   ├── 03_lidar_processing.ipynb    Point cloud → bare-earth DEM
│   ├── 04_archaeological_viz.ipynb  SVF, LRM, hillshade products
│   ├── 05_feature_detection.ipynb   Automated mound/kiva detection
│   └── 06_web_map.ipynb             Export interactive Leaflet map
│
├── scripts/
│   ├── download_dem.py      CLI tile downloader
│   ├── run_pipeline.py      End-to-end pipeline runner
│   └── render_site.py       forge3d CLI renderer
│
├── data/
│   ├── raw/                 ← LAZ tiles (gitignored, large)
│   ├── processed/           ← GeoTIFFs (gitignored, generated)
│   ├── renders/             ← PNG renders (gitignored, generated)
│   └── vectors/             ← GeoJSON features (committed ✓)
│
├── web/
│   └── index.html           GitHub Pages interactive map
│
└── docs/
    └── field_notes.md       Survey methodology notes
```

---

## Pipeline

### Data Sources

| Source | What | Access |
|--------|------|--------|
| [USGS 3DEP](https://apps.nationalmap.gov/downloader/) | 1m LiDAR point clouds | Free, no account |
| [OpenTopography](https://opentopography.org) | Alternative LiDAR API | Free API key |
| NPS GIS | Site boundary polygons | Public |

### Processing

```
LAZ tiles → ground filter → bare-earth DEM
    → hillshade (4 azimuths)
    → Sky-View Factor (SVF)         ← best for road berms, kiva depressions
    → Local Relief Model (LRM)      ← best for mounds, platform edges
    → blob detection + Hough circles → candidate_features.geojson
    → forge3d path_tracing render   ← publication 3D visualization
    → Leaflet web map               ← interactive site browser
```

---

## forge3d Rendering

Project Kiva uses [forge3d](https://github.com/milos-agathon/forge3d) for GPU-accelerated 3D terrain visualization. The headless path tracer works without the interactive viewer binary:

```python
from forge3d import path_tracing
from forge3d._png import save_png

tracer = path_tracing.create_path_tracer(3840, 2160, max_bounces=2)
camera = path_tracing.make_camera(
    origin=(ox, oy, oz), look_at=(cx, cy, cz),
    up=(0, 0, 1), fov_y=45.0, aspect=16/9, exposure=1.0
)
rgba = path_tracing.render_rgba(tracer, dem_array, camera, samples=64)
save_png('render.png', rgba)
```

See `notebooks/02_render_forge3d.ipynb` and `scripts/render_site.py` for the full workflow.

---

## Web Map

The interactive map is deployed to GitHub Pages:  
**`https://bdgroves.github.io/project-kiva`**

Features:
- Satellite / topo / terrain basemap toggle
- Known site locations with historical notes
- Automated candidate feature detections
- Schematic road/canal segment overlays

---

## References

- Lekson, S.H. (1999). *The Chaco Meridian.* AltaMira Press.
- Chase, A. et al. (2011). Airborne LiDAR, archaeology, and the ancient Maya landscape. *Journal of Archaeological Science*, 38(2).
- Evans, D. et al. (2013). Uncovering archaeological landscapes at Angkor using LiDAR. *PNAS*, 110(31).
- Opitz, R. & Cowley, D. (Eds.) (2013). *Interpreting Archaeological Topography.* Oxbow Books.

---

## License

Code: MIT. Data products derived from USGS 3DEP are public domain.

*This is a learning/portfolio project. Feature detections are unverified and should not be cited as archaeological findings.*
