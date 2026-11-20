"""Encode a directory of timestamped frames into a time-lapse with ffmpeg.

Frames are expected to be named <sat>_YYYYmmddTHHMM.jpg (as written by
make_year.py). The full time grid is rebuilt from the first/last frame and
--freq; any missing timestamp repeats the previous frame so time stays uniform.

Example
  python movie.py ~/data/goes/frames goes18_year.mp4 --size 4320 --fps 30
"""
import argparse
import glob
import os
import subprocess
import tempfile

import pandas as pd


def frame_list(frame_dir, freq='10min'):
    files = sorted(glob.glob(os.path.join(frame_dir, '*_????????T????.jpg')))
    if not files:
        raise FileNotFoundError(f'no frames in {frame_dir}')
    by_time = {pd.to_datetime(os.path.basename(f)[-17:-4], format='%Y%m%dT%H%M'): f
               for f in files}
    grid = pd.date_range(min(by_time), max(by_time), freq=freq)
    out, prev, missing = [], None, 0
    for t in grid:
        if t in by_time:
            prev = by_time[t]
        else:
            missing += 1
        out.append(prev)
    print(f'{len(grid)} timestamps, {len(files)} frames, {missing} filled by repeat')
    return out


def main(frame_dir, movie_name, size=4320, fps=30, crf=18, freq='10min',
         codec='libx265'):
    frames = frame_list(frame_dir, freq)
    with tempfile.TemporaryDirectory() as tmp:
        # numbered symlinks -> ffmpeg image2 demuxer, streamed one at a time
        for i, f in enumerate(frames):
            os.symlink(os.path.abspath(f), os.path.join(tmp, f'{i:06d}.jpg'))
        cmd = ['ffmpeg', '-y', '-framerate', str(fps),
               '-i', os.path.join(tmp, '%06d.jpg'),
               '-vf', f'scale={size}:{size}:flags=lanczos',
               '-c:v', codec, '-crf', str(crf), '-preset', 'slow',
               '-pix_fmt', 'yuv420p10le']
        if codec == 'libx265':
            cmd += ['-tag:v', 'hvc1']  # plays in QuickTime
        cmd += [movie_name]
        print(' '.join(cmd))
        subprocess.run(cmd, check=True)
    return movie_name


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('frame_dir')
    ap.add_argument('movie_name')
    ap.add_argument('--size', type=int, default=4320)
    ap.add_argument('--fps', type=int, default=30)
    ap.add_argument('--crf', type=int, default=18)
    ap.add_argument('--freq', default='10min')
    ap.add_argument('--codec', default='libx265')
    a = ap.parse_args()
    main(a.frame_dir, a.movie_name, a.size, a.fps, a.crf, a.freq, a.codec)
