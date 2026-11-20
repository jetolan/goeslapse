"""Render the same timestamps with each pipeline so they can be compared.

For every timestamp and method writes, into --out (default ./compare):
  <ts>_<method>_full.jpg    full disk, 5424 x 5424
  <ts>_<method>_crop.png    2048 x 2048 crop at 0.5 km/px (same region for all)
  <ts>_montage.jpg          methods side by side (full disk on top, crops below)
  summary.csv               runtime and peak memory per render

Usage: python compare_frames.py [--sat goes18] [--times "2025-06-21 21:10" ...]
"""
import argparse
import concurrent.futures as cf
import os
import resource
import shutil
import sys
import time

import cv2
import numpy as np
import pandas as pd

DEFAULT_TIMES = [
    '2025-03-20 21:10',  # spring equinox, local noon at 137.2W
    '2025-06-21 21:10',  # summer solstice noon
    '2025-06-21 09:10',  # summer solstice midnight
    '2025-09-22 15:30',  # autumn equinox, terminator across the disk
    '2025-12-21 21:10',  # winter solstice noon
]
METHODS = ['legacy', 'satpy_true_color', 'satpy_night_ir']
FULL = 5424
CROP = 2048            # crop size in 0.5 km pixels
CROP_CENTER = (0.60, 0.33)  # fraction of disk (x, y): NE Pacific / W North America


def _render(method, date, sat, work_dir, out_file):
    """Runs in a fresh process; returns (seconds, peak RSS in GB)."""
    t0 = time.time()
    if method == 'legacy':
        import adjust_image
        import rgb_frame
        bands = rgb_frame.get_bands(date, sat, [1, 2, 3], 'F', work_dir)
        rgb = rgb_frame.weight_bands(rgb_frame.resample_bands(bands))
        stack = rgb_frame.stack_bands(rgb)
        with __import__('rasterio').open(stack) as src:
            n = src.width  # 10848: legacy pipeline works at 1 km
        adjust_image.main(stack, out_file=out_file, w=n, h=n)
    else:
        import dask
        import satpy_frame
        dask.config.set(num_workers=os.cpu_count())
        comp = 'true_color' if method == 'satpy_true_color' \
            else 'true_color_with_night_ir_nobg'
        files = satpy_frame.download(date, sat, 'F', satpy_frame.COMPOSITES[comp],
                                     os.path.join(work_dir, 'nc'))
        satpy_frame.render(files, out_file, comp, resolution='finest')
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_gb = rss / 1e9 if sys.platform == 'darwin' else rss / 1e6
    return time.time() - t0, rss_gb


def _crop_box(width):
    """Crop window in pixels of an image `width` wide (same ground area)."""
    c = CROP * width // 21696
    cx, cy = int(CROP_CENTER[0] * width), int(CROP_CENTER[1] * width)
    return cy - c // 2, cy + c // 2, cx - c // 2, cx + c // 2


def derive_outputs(native_file, full_file, crop_file):
    im = cv2.imread(native_file, cv2.IMREAD_COLOR)
    y0, y1, x0, x1 = _crop_box(im.shape[1])
    crop = cv2.resize(im[y0:y1, x0:x1], (CROP, CROP),
                      interpolation=cv2.INTER_CUBIC)
    cv2.imwrite(crop_file, crop)
    full = cv2.resize(im, (FULL, FULL), interpolation=cv2.INTER_AREA)
    cv2.imwrite(full_file, full, [cv2.IMWRITE_JPEG_QUALITY, 95])


def montage(paths_full, paths_crop, labels, out_file, tile=1200):
    cols = []
    for pf, pc, lab in zip(paths_full, paths_crop, labels):
        top = cv2.resize(cv2.imread(pf), (tile, tile), interpolation=cv2.INTER_AREA)
        bot = cv2.resize(cv2.imread(pc), (tile, tile), interpolation=cv2.INTER_AREA)
        col = np.vstack([top, bot])
        cv2.putText(col, lab, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5,
                    (255, 255, 255), 3, cv2.LINE_AA)
        cols.append(col)
    cv2.imwrite(out_file, np.hstack(cols), [cv2.IMWRITE_JPEG_QUALITY, 90])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sat', default='goes18')
    ap.add_argument('--times', nargs='+', default=DEFAULT_TIMES)
    ap.add_argument('--methods', nargs='+', default=METHODS, choices=METHODS)
    ap.add_argument('--out', default='compare')
    ap.add_argument('--keep-raw', action='store_true')
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    summary_csv = os.path.join(args.out, 'summary.csv')
    rows = pd.read_csv(summary_csv).to_dict('records') \
        if os.path.exists(summary_csv) else []
    for t in args.times:
        date = pd.to_datetime(t)
        ts = f'{date:%Y%m%dT%H%M}'
        work = os.path.join(args.out, 'work', ts)
        fulls, crops = [], []
        for m in args.methods:
            full = os.path.join(args.out, f'{ts}_{m}_full.jpg')
            crop = os.path.join(args.out, f'{ts}_{m}_crop.png')
            if not (os.path.exists(full) and os.path.exists(crop)):
                native = os.path.join(work, f'{ts}_{m}_native.png')
                print(f'--- {ts} {m}')
                with cf.ProcessPoolExecutor(max_workers=1) as ex:
                    secs, gb = ex.submit(_render, m, date, args.sat, work,
                                         native).result()
                derive_outputs(native, full, crop)
                os.remove(native)
                rows = [r for r in rows if not (r['time'] == ts and r['method'] == m)]
                rows.append({'time': ts, 'method': m,
                             'seconds': round(secs, 1), 'peak_gb': round(gb, 2)})
                pd.DataFrame(rows).to_csv(summary_csv, index=False)
                print(f'    {secs:.0f} s, peak {gb:.1f} GB')
            fulls.append(full)
            crops.append(crop)
        montage(fulls, crops, args.methods,
                os.path.join(args.out, f'{ts}_montage.jpg'))
        if not args.keep_raw:
            shutil.rmtree(work, ignore_errors=True)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == '__main__':
    main()
