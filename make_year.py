"""Render every frame of a time-lapse, streaming raw data (download -> render -> delete).

Resumable: frames that already exist in --out are skipped, so the job can be
stopped and restarted (e.g. on a spot instance). Results are appended to
<out>/manifest.csv (time, status, file, seconds).

Default period is the 2025 -> 2026 spring equinox solar year for GOES-18:
2025-03-20 09:01 UTC -> 2026-03-20 14:46 UTC at a 10-minute cadence.

Examples
  # one test day locally
  python make_year.py --start "2025-06-21 00:00" --end "2025-06-21 23:50" --out ~/data/goes/day
  # whole year on an EC2 box, frames straight to S3
  python make_year.py --out s3://my-bucket/goeslapse/frames --work-dir /mnt/scratch --workers 8
"""
import argparse
import concurrent.futures as cf
import csv
import os
import shutil
import time

import pandas as pd

METHODS = ('legacy', 'true_color', 'true_color_with_night_ir_nobg',
           'true_color_soft', 'true_color_soft_wide')


def frame_name(sat, date):
    return f"{sat}_{pd.to_datetime(date):%Y%m%dT%H%M}.jpg"


def _fs(out):
    if out.startswith('s3://'):
        import s3fs
        return s3fs.S3FileSystem()
    return None


def existing_frames(out):
    fs = _fs(out)
    try:
        names = fs.ls(out) if fs else os.listdir(out)
    except FileNotFoundError:
        return set()
    return {os.path.basename(n) for n in names}


def render_one(date, sat, method, resolution, size, out, work_root):
    """Worker: returns (time, status, file, seconds)."""
    t0 = time.time()
    date = pd.to_datetime(date)
    name = frame_name(sat, date)
    work = os.path.join(work_root, f'{date:%Y%m%dT%H%M}')
    local = os.path.join(work, name)
    try:
        if method == 'legacy':
            import rgb_frame
            rgb_frame.main(date, sat, 'F', work, work_dir=os.path.join(work, 'raw'),
                           clean=False, size=size or 5424)
        else:
            import satpy_frame
            files = satpy_frame.download(date, sat, 'F',
                                         satpy_frame.COMPOSITES[method],
                                         os.path.join(work, 'raw'))
            satpy_frame.render(files, local, method, resolution, size)
        fs = _fs(out)
        if fs:
            fs.put(local, f"{out.rstrip('/')}/{name}")
        else:
            shutil.move(local, os.path.join(out, name))
        status = 'ok'
    except FileNotFoundError as e:   # no scan near this time (data gap)
        status, name = f'missing: {e}', ''
    except Exception as e:           # corrupt file etc. - logged, retried on rerun
        status, name = f'error: {type(e).__name__}: {e}', ''
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return f'{date:%Y-%m-%d %H:%M}', status, name, round(time.time() - t0, 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sat', default='goes18')
    ap.add_argument('--start', default='2025-03-20 09:00')
    ap.add_argument('--end', default='2026-03-20 14:50')
    ap.add_argument('--freq', default='10min')
    ap.add_argument('--method', default='true_color_soft_wide', choices=METHODS)
    ap.add_argument('--resolution', default='finest', choices=('finest', 'coarsest'),
                    help='satpy grid: finest = 0.5 km (21696 px)')
    ap.add_argument('--size', type=int, default=None,
                    help='output frame size in px (must divide the grid, e.g. 5424, 10848)')
    ap.add_argument('--out', required=True, help='local dir or s3:// prefix')
    ap.add_argument('--work-dir', default=None, help='scratch for raw files')
    ap.add_argument('--workers', type=int, default=1,
                    help='parallel frames; satpy at 0.5 km needs ~8-12 GB RAM each')
    args = ap.parse_args()

    if not args.out.startswith('s3://'):
        args.out = os.path.expanduser(args.out)
        os.makedirs(args.out, exist_ok=True)
    work_root = os.path.expanduser(args.work_dir or os.path.join(
        args.out if not args.out.startswith('s3://') else '/tmp', '_work'))
    os.makedirs(work_root, exist_ok=True)

    dates = pd.date_range(args.start, args.end, freq=args.freq)
    have = existing_frames(args.out)
    todo = [d for d in dates if frame_name(args.sat, d) not in have]
    print(f'{len(dates)} frames in period, {len(dates) - len(todo)} done, '
          f'{len(todo)} to render')

    manifest = os.path.join(args.out if not args.out.startswith('s3://')
                            else work_root, 'manifest.csv')
    new = not os.path.exists(manifest)
    with open(manifest, 'a', newline='') as fh, \
            cf.ProcessPoolExecutor(max_workers=args.workers,
                                   max_tasks_per_child=1) as ex:
        w = csv.writer(fh)
        if new:
            w.writerow(['time', 'status', 'file', 'seconds'])
        futs = [ex.submit(render_one, d, args.sat, args.method, args.resolution,
                          args.size, args.out, work_root) for d in todo]
        for i, f in enumerate(cf.as_completed(futs), 1):
            row = f.result()
            w.writerow(row)
            fh.flush()
            print(f'[{i}/{len(todo)}] {row[0]} {row[1]} {row[3]}s')
    if args.out.startswith('s3://'):
        _fs(args.out).put(manifest, f"{args.out.rstrip('/')}/manifest.csv")


if __name__ == '__main__':
    main()
