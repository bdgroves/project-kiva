"""Sanity checks for the relief maths on synthetic ground."""
import numpy as np

from kiva import relief as R

RES = 0.5


def ground():
    y, x = np.mgrid[0:300, 0:300].astype(np.float32)
    dem = 0.02 * x                                                     # gentle rise to the east
    dem -= np.where((x - 80) ** 2 + (y - 80) ** 2 < 12 ** 2, 1.0, 0)   # a 1 m deep pit (kiva)
    dem += np.where(np.abs(x - 220) < 2, 0.6, 0)                       # a 60 cm wall
    return dem


def test_hillshade_faces_the_sun():
    dem = ground()
    west = R.hillshade(dem, RES, azimuth=270)[150, 150]
    east = R.hillshade(dem, RES, azimuth=90)[150, 150]
    assert west > east          # the plane rises east, so it faces west


def test_local_relief_finds_pit_and_wall():
    lrm = R.local_relief(ground(), RES, 15)
    assert lrm[80, 80] < -0.3
    assert lrm[150, 220] > 0.3
    assert abs(lrm[250, 150]) < 0.05


def test_sky_view_and_openness():
    dem = ground()
    up, dn = R.horizon_scan(dem, RES, radius_m=4)
    svf = R.sky_view(up)
    pos, neg = R.openness(up, dn)
    assert svf[80, 80 - 11] < svf[250, 150]       # inside the pit edge sees less sky
    assert neg[150, 220] < neg[250, 150]          # wall top: ground falls away


def test_nodata_survives():
    dem = ground()
    dem[10:20, 10:20] = np.nan
    out = R.all_products(dem, RES, horizon_m=3)
    assert np.isnan(out["composite"][15, 15])
    assert np.isfinite(out["composite"][150, 150])
