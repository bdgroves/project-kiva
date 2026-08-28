"""
scripts/run_pipeline.py

Ground-classified point cloud -> bare-earth DEM -> Local Relief Model.
LRM strips out broad terrain trend (the canyon slope) and keeps only the
fine-scale relief -- wall stubs, room depressions, midden mounds -- exactly
the signal that reveals structure invisible in a plain hillshade.
"""
import numpy as np
import laspy
import rasterio
from rasterio.transform import from_origin
from scipy.ndimage import uniform_filter, gaussian_filter
from pathlib import Path

LAZ_PATH = Path(r"C:\Users\brook\Documents\project-kiva\data\raw\pueblo_bonito_13SBV3394.laz")
OUT_DIR = Path(r"C:\Users\brook\Documents\project-kiva\data\processed")
OUT_DIR.mkdir(parents=True, exist_ok=True)

RES = 1.0  # meters
LRM_SMOOTH_RADIUS_M = 15  # per config.yaml lrm.smoothing_radius

print("Reading point cloud...")
las = laspy.read(str(LAZ_PATH))
ground = las.classification == 2
x = np.asarray(las.x[ground], dtype=np.float64)
y = np.asarray(las.y[ground], dtype=np.float64)
z = np.asarray(las.z[ground], dtype=np.float64)
print(f"  {ground.sum():,} ground points of {len(las.points):,} total")

xmin, xmax = x.min(), x.max()
ymin, ymax = y.min(), y.max()
ncols = int(np.ceil((xmax - xmin) / RES))
nrows = int(np.ceil((ymax - ymin) / RES))
print(f"  grid: {ncols} x {nrows} @ {RES}m")

col = ((x - xmin) / RES).astype(int).clip(0, ncols - 1)
row = ((ymax - y) / RES).astype(int).clip(0, nrows - 1)  # flip: row 0 = north

flat_idx = row * ncols + col
sums = np.bincount(flat_idx, weights=z, minlength=nrows * ncols)
counts = np.bincount(flat_idx, minlength=nrows * ncols)

dem = np.full(nrows * ncols, np.nan, dtype=np.float32)
has_data = counts > 0
dem[has_data] = sums[has_data] / counts[has_data]
dem = dem.reshape(nrows, ncols)

# Fill small nodata gaps (rare with this point density) via nearest-neighbor
nodata_mask = np.isnan(dem)
print(f"  nodata cells: {nodata_mask.sum()} of {dem.size} ({100*nodata_mask.mean():.2f}%)")
if nodata_mask.any():
    from scipy.ndimage import distance_transform_edt
    idx = distance_transform_edt(nodata_mask, return_distances=False, return_indices=True)
    dem = dem[tuple(idx)]

transform = from_origin(xmin, ymax, RES, RES)
crs = "EPSG:6342"

dem_path = OUT_DIR / "pueblo_bonito_dem_1m.tif"
with rasterio.open(dem_path, "w", driver="GTiff", height=nrows, width=ncols,
                    count=1, dtype="float32", crs=crs, transform=transform,
                    nodata=-9999) as dst:
    dst.write(dem, 1)
print(f"Wrote {dem_path}")

# Local Relief Model: DEM minus a heavily smoothed version of itself.
# This removes the canyon's broad slope and leaves only sub-metre relief.
print("Computing Local Relief Model...")
smooth_px = max(int(round(LRM_SMOOTH_RADIUS_M / RES)), 3)
trend = gaussian_filter(dem, sigma=smooth_px)
lrm = dem - trend

lrm_path = OUT_DIR / "pueblo_bonito_lrm.tif"
with rasterio.open(lrm_path, "w", driver="GTiff", height=nrows, width=ncols,
                    count=1, dtype="float32", crs=crs, transform=transform,
                    nodata=-9999) as dst:
    dst.write(lrm.astype("float32"), 1)
print(f"Wrote {lrm_path}")

print(f"\nDEM z-range: {np.nanmin(dem):.2f} to {np.nanmax(dem):.2f} m")
print(f"LRM range: {np.nanmin(lrm):.2f} to {np.nanmax(lrm):.2f} m (should be small, near zero-centered)")
