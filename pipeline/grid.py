"""The model grid: one 30 m UTM 29N raster definition shared by every layer."""

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

from pipeline import config


def model_grid():
    """Return (transform, width, height) of the canonical grid covering config.AOI_BBOX."""
    to_utm = Transformer.from_crs(config.CRS_WEB, config.CRS_WORK, always_xy=True)
    lon0, lat0, lon1, lat1 = config.AOI_BBOX
    xs, ys = to_utm.transform([lon0, lon0, lon1, lon1], [lat0, lat1, lat0, lat1])
    r = config.GRID_RES_M
    xmin, xmax = np.floor(min(xs) / r) * r, np.ceil(max(xs) / r) * r
    ymin, ymax = np.floor(min(ys) / r) * r, np.ceil(max(ys) / r) * r
    transform = Affine(r, 0, xmin, 0, -r, ymax)
    return transform, int((xmax - xmin) / r), int((ymax - ymin) / r)


def profile(dtype="float32", nodata=None):
    transform, width, height = model_grid()
    return dict(driver="GTiff", width=width, height=height, count=1, dtype=dtype,
                crs=config.CRS_WORK, transform=transform, nodata=nodata,
                compress="deflate", tiled=True)


def align_to_grid(src_path, dst_path, resampling=Resampling.nearest, dtype="float32", nodata=None):
    """Warp any raster onto the canonical grid so all layers share identical cells."""
    prof = profile(dtype, nodata)
    out = np.full((prof["height"], prof["width"]), nodata if nodata is not None else 0, dtype=dtype)
    with rasterio.open(src_path) as src:
        reproject(rasterio.band(src, 1), out, dst_transform=prof["transform"], dst_crs=prof["crs"],
                  dst_nodata=nodata, resampling=resampling)
    with rasterio.open(dst_path, "w", **prof) as dst:
        dst.write(out, 1)
    return dst_path


def read(path):
    with rasterio.open(path) as src:
        return src.read(1)


def write(path, array, dtype=None, nodata=None):
    dtype = dtype or array.dtype.name
    with rasterio.open(path, "w", **profile(dtype, nodata)) as dst:
        dst.write(array.astype(dtype), 1)
    return path
