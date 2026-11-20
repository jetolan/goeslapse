import rasterio
import numpy as np
import pandas as pd
import os
import shutil
from rasterio.warp import calculate_default_transform, reproject, Resampling

import nctogtiff
import get_nc
import weight
import adjust_image

def get_bands(date, sat, bands, frame, local_dir, dryrun=False):
    band_files = []
    nc_dir = f'{local_dir}/nc/'
    tiff_dir = nc_dir.replace('/nc/', '/tiff/')
    if not os.path.exists(nc_dir):
        os.makedirs(nc_dir)
    if not os.path.exists(tiff_dir):
        os.makedirs(tiff_dir)
    for band in bands:
        outfile = get_nc.main(sat, band, frame, date,
                              local_dir=nc_dir, dryrun=dryrun)
        basename = os.path.basename(outfile)
        tiff = basename.replace('.nc', '.tiff')
        tiff_path = f'{tiff_dir}{tiff}'
        if not dryrun:
            try:
                tiff = nctogtiff.main(outfile, tiff_path)
            except RuntimeError:
                #redownload
                 outfile = get_nc.main(sat, band, frame, date,
                                       local_dir=nc_dir, replace=True)
                 tiff = nctogtiff.main(outfile, tiff_path)
        band_files.append(tiff)
    return band_files


def resample_bands(band_files):
    # determine largest pixel size of all bands in collection
    resx, resy = [], []
    for band in band_files:
        with rasterio.open(band) as src:
            resx.append(src.res[0])
            resy.append(src.res[1])
    resx = np.array(resx)
    resy = np.array(resy)
    if np.argmax(abs(resx)) != np.argmax(abs(resy)):
        raise ValueError('non square max pixels')

    resized_files = []
    low_ind = np.argmax(resx)
    with rasterio.open(band_files.pop(low_ind)) as low:
        resized_files.append(low.name)
        for band in band_files:
            with rasterio.open(band) as hi:
                if hi.res[0] == low.res[0] and hi.res[1] == low.res[1]:
                    resized_files.append(band)
                    continue
                else:
                    transform, width, height = calculate_default_transform(
                        low.crs, hi.crs, low.width, low.height, *low.bounds)

                    kwargs = src.meta.copy()
                    kwargs.update({
                        'crs': low.crs,
                        'transform': transform,
                        'width': width,
                        'height': height
                    })

                    outf = band.replace('.tif', 'resampled.tif')
                    with rasterio.open(outf, 'w', **kwargs) as dst:
                        for i in range(1, dst.count + 1):
                            reproject(
                                source=rasterio.band(hi, i),
                                destination=rasterio.band(dst, i),
                                src_transform=hi.transform,
                                src_crs=hi.crs,
                                dst_transform=transform,
                                dst_crs=low.crs,
                                resampling=Resampling.nearest)
                    resized_files.append(outf)

    return resized_files


def weight_bands(resized_files):
    blue = [f for f in resized_files if "C01" in f][0]
    red = [f for f in resized_files if "C02" in f][0]
    nir = [f for f in resized_files if "C03" in f][0]
    in_ext = os.path.splitext(nir)[1]
    nr = nir.replace(in_ext, '_nr.tif')
    green = nir.replace(in_ext, '_green.tif')
    weight.main(nir, red, (1, 3), nr)
    weight.main(nr, blue, (4, 8), green)
    file_list = [red, green, blue]
    return file_list


def stack_bands(rgb_files, outfile=None):
    if outfile is None:
        stack = rgb_files[0].replace('.tif', 'stack.tif')

    with rasterio.open(rgb_files[0]) as src:
        out_meta = src.meta.copy()

    out_meta.update({"count": len(rgb_files),
                     "nodata": 0,
                     "photometric": "RGB",
                     "crompress": "lzw",
                     })

    with rasterio.open(stack, 'w', **out_meta) as dest:
        for band_nr, ff in enumerate(rgb_files, start=1):
            with rasterio.open(ff) as src:
                data = src.read(1)
                dest.write(data, band_nr)

    return stack

def main(date, sat, bands, frame, local_dir, clean=True, uselocal=True):
    """
    uselocal:
    """

    tmp_dir = f"{local_dir}/tmp/"

    if uselocal:
        band_files = get_bands(date, sat, bands, frame, tmp_dir, dryrun=True)
        fname = os.path.basename(sorted(band_files)[1])
        in_ext = os.path.splitext(fname)[1]
        out_file = f"{local_dir}{fname.replace(in_ext, 'resampledstack.jpg')}"
        if os.path.exists(out_file):
            print(f"{out_file} exists and uselocal=True")
            return out_file

    band_files = get_bands(
        date, sat, bands, frame, tmp_dir, dryrun=False)
    resized_files = resample_bands(band_files)
    rgb_files = weight_bands(resized_files)
    stacked_file = stack_bands(rgb_files)

    # make 0800 & 0900 images black
    # as some of these are usually corrupt
    if date.hour in [8, 9]:
        print('night')
        # TODO: make "black" TIFF and put in here.

    fname = os.path.basename(stacked_file)
    in_ext = os.path.splitext(fname)[1]
    out_file = f"{local_dir}{fname.replace(in_ext, '.jpg')}"
    out_file = adjust_image.main(stacked_file, out_file=out_file)

    if clean:
        nc_dir = f"{tmp_dir}/nc/"
        tiff_dir = f"{tmp_dir}/tiff/"
        shutil.rmtree(tiff_dir)
        shutil.rmtree(nc_dir)
    return out_file


if __name__ == "__main__":
    sat = 'goes17'
    bands = [1, 2, 3]  # 1:blue, 2:red, 3:nir
    frame = 'F'
    local_dir = "/Users/jetolan/data/goes/"
    date = pd.to_datetime('2021-06-13 20:50')
    main(date, sat, bands, frame, local_dir, clean=False, uselocal=True)
