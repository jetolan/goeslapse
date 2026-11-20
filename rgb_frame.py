"""Original (2022) true-color frame pipeline, fixed for current GOES data.

nc -> GeoTIFF (nctogtiff) -> resample all bands to the coarsest grid ->
synthetic green from weighted red/nir/blue (weight) -> RGB stack ->
8-bit LUT colour mapping (adjust_image).
"""
import os
import shutil

import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling

import adjust_image
import get_nc
import nctogtiff
import weight


def frame_name(sat, date, suffix='', ext='.jpg'):
    """Timestamp-based frame filename, e.g. goes18_20250320T2110.jpg"""
    return f"{sat}_{pd.to_datetime(date):%Y%m%dT%H%M}{suffix}{ext}"


def get_bands(date, sat, bands, frame, work_dir):
    """Download each band and convert it to a GeoTIFF. Returns tiff paths."""
    nc_dir = os.path.join(work_dir, 'nc')
    tiff_dir = os.path.join(work_dir, 'tiff')
    os.makedirs(nc_dir, exist_ok=True)
    os.makedirs(tiff_dir, exist_ok=True)
    band_files = []
    for band in bands:
        ncfile = get_nc.main(sat, band, frame, date, local_dir=nc_dir)
        tiff_path = os.path.join(
            tiff_dir, os.path.basename(ncfile).replace('.nc', '.tif'))
        try:
            nctogtiff.main(ncfile, tiff_path)
        except (RuntimeError, OSError):
            # corrupt/partial download: fetch again
            ncfile = get_nc.main(sat, band, frame, date,
                                 local_dir=nc_dir, replace=True)
            nctogtiff.main(ncfile, tiff_path)
        band_files.append(tiff_path)
    return band_files


def resample_bands(band_files):
    """Resample every band onto the grid of the coarsest band.

    All ABI channels share the same fixed grid, differing only by integer
    factors (0.5/1/2 km), so this is a plain area-average downsample.
    """
    res = []
    for f in band_files:
        with rasterio.open(f) as src:
            res.append(abs(src.res[0]))
    with rasterio.open(band_files[int(np.argmax(res))]) as low:
        target = low.profile
    resized_files = []
    for f in band_files:
        with rasterio.open(f) as src:
            if src.width == target['width'] and src.height == target['height']:
                resized_files.append(f)
                continue
            data = src.read(1, out_shape=(target['height'], target['width']),
                            resampling=Resampling.average)
        outf = f.replace('.tif', '_resampled.tif')
        with rasterio.open(outf, 'w', **target) as dst:
            dst.write(data, 1)
        resized_files.append(outf)
    return resized_files


def weight_bands(resized_files):
    """Synthetic green: (red*1 + nir*3)/4 weighted 4:8 with blue."""
    blue = [f for f in resized_files if "C01_" in f][0]
    red = [f for f in resized_files if "C02_" in f][0]
    nir = [f for f in resized_files if "C03_" in f][0]
    nr = nir.replace('.tif', '_nr.tif')
    green = nir.replace('.tif', '_green.tif')
    weight.main(nir, red, (1, 3), nr)
    weight.main(nr, blue, (4, 8), green)
    return [red, green, blue]


def stack_bands(rgb_files, outfile=None):
    if outfile is None:
        outfile = rgb_files[0].replace('.tif', '_stack.tif')
    with rasterio.open(rgb_files[0]) as src:
        out_meta = src.meta.copy()
    out_meta.update({"count": len(rgb_files),
                     "nodata": 0,
                     "photometric": "RGB",
                     "compress": "lzw"})
    with rasterio.open(outfile, 'w', **out_meta) as dest:
        for band_nr, ff in enumerate(rgb_files, start=1):
            with rasterio.open(ff) as src:
                dest.write(src.read(1), band_nr)
    return outfile


def main(date, sat, frame, out_dir, bands=(1, 2, 3), work_dir=None,
         clean=True, size=5424, lut_file=None):
    """Render one frame; returns the output jpg path (skips if it exists)."""
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, frame_name(sat, date))
    if os.path.exists(out_file):
        print(f"{out_file} exists, skipping")
        return out_file
    if work_dir is None:
        work_dir = os.path.join(out_dir, 'tmp')

    band_files = get_bands(date, sat, list(bands), frame, work_dir)
    resized_files = resample_bands(band_files)
    rgb_files = weight_bands(resized_files)
    stacked_file = stack_bands(rgb_files)
    kwargs = {} if lut_file is None else {'lut_file': lut_file}
    out_file = adjust_image.main(stacked_file, out_file=out_file,
                                 w=size, h=size, **kwargs)
    if clean:
        shutil.rmtree(work_dir, ignore_errors=True)
    return out_file


if __name__ == "__main__":
    print(main(pd.to_datetime('2025-03-20 21:10'), 'goes18', 'F',
               os.path.expanduser('~/data/goes/test'), clean=False))
