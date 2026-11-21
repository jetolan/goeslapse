# goeslapse

Full-disk, true-color time-lapses of Earth from the GOES geostationary weather
satellites, built from NOAA's raw ABI Level-1b data on AWS.

The current target is a **solar year**: spring equinox 2025-03-20 09:01 UTC to
spring equinox 2026-03-20 14:46 UTC, from **GOES-18 (GOES-West, 137.2°W)**, one
frame every 10 minutes (~52,600 frames).

## Data

NOAA publishes every ABI scan in public S3 buckets (`us-east-1`, no AWS account
or credentials needed):

| Bucket | Satellite | Status |
|---|---|---|
| `s3://noaa-goes19` | GOES-19 | GOES-East (75.2°W) since 2025-04-07 |
| `s3://noaa-goes18` | GOES-18 | GOES-West (137.2°W) since 2023-01 |
| `s3://noaa-goes16` | GOES-16 | GOES-East until 2025-04; archive |
| `s3://noaa-goes17` | GOES-17 | Retired 2023; archive (2018–2023) |

Full-disk product `ABI-L1b-RadF`, scan mode 6: one scan every 10 minutes. True
color uses channels C01 (blue, 1 km), C02 (red, 0.5 km, 21696×21696 px) and C03
(near-IR "veggie", 1 km); the night-side IR blend adds C13 (10.3 µm, 2 km).
GDAL needs its separate netCDF driver (`libgdal-netcdf`, included in the
environment) for the legacy pipeline.

One full-disk scan of C01–C03 is ~590 MB of NetCDF, so a year at 10-minute
cadence is **~31 TB** of downloads. Raw files are therefore never kept: each
frame is downloaded, rendered and deleted.

## Setup

```sh
conda env create -f environment.yml
conda activate goes
```

The first satpy run downloads pyspectral's Rayleigh-correction tables (~100 MB).

## Usage

**1. Compare rendering methods** on a handful of dates (equinox/solstice noon,
midnight, terminator):

```sh
python compare_frames.py               # writes compare/*_montage.jpg + summary.csv
```

Methods:
- `legacy`: the original 2022 pipeline (`rgb_frame.py`): 1 km bands, simple
  weighted synthetic green, 8-bit LUT fitted to a GOES-17 reference image.
- `satpy_true_color`: satpy `true_color` at full 0.5 km, with pyspectral
  Rayleigh correction and satpy's synthetic green.
- `satpy_soft` / `satpy_soft_wide`: satpy's corrected `true_color` on the lit
  disk, cross-faded by sun zenith angle (70→90° / 50→90°) into the uncorrected
  `true_color_nocorr`, so brightness falls off gradually to a dark night side.
  This avoids `true_color`'s hard terminator edge and saturated twilight crescent
  (composites `true_color_soft`, `true_color_soft_wide` in `satpy_config/`).
- `satpy_night_ir`: as above, with the night side filled with C13 infrared
  cloud tops (`true_color_with_night_ir_nobg`, defined in
  `satpy_config/`; satpy's stock `true_color_with_night_ir` currently fails
  because its Black Marble background download no longer matches its checksum).

**2. Render frames** (resumable, so re-running skips frames that already exist):

```sh
# one test day
python make_year.py --start "2025-06-21 00:00" --end "2025-06-21 23:50" \
    --out ~/data/goes/day --size 5424
# the whole solar year (defaults), frames straight to S3
python make_year.py --out s3://<bucket>/goeslapse/frames --size 10848 \
    --work-dir /mnt/scratch --workers 8
```

Each run appends to `manifest.csv` in the output. Missing or corrupt scans are
logged there and retried on the next run.

**3. Encode the movie** (gaps are filled by repeating the previous frame):

```sh
python movie.py ~/data/goes/frames goes18_2025.mp4 --size 4320 --fps 30
```

At 30 fps the full year is ~29 minutes. HEVC (libx265, 10-bit) handles square
frames up to ~5900 px (level 6.x). Keep the frames as the master copy to
re-encode at other sizes, frame rates or crops.

## Storage and compute

| Item | Size |
|---|---|
| Raw download (streamed, not stored) | ~31 TB |
| Frames, 5424² JPEG q95 (2 km/px) | ~250–350 GB |
| Frames, 10848² JPEG q95 (1 km/px) | ~1–1.3 TB |
| Frames, 21696² (native 0.5 km/px) | ~4–5 TB |
| Final videos | 5–40 GB |

**Recommended: run on AWS EC2 in `us-east-1`**, next to the NOAA buckets.
Reading the public data there is free and fast (GB/s). Use a large instance (e.g.
32–64 vCPU, 128–256 GB RAM, spot pricing; satpy at 0.5 km uses ~8–12 GB per
worker), write frames to S3, encode the video on the instance, and download only
the videos (internet egress is ~$0.09/GB).

**Local alternative:** stream the 31 TB over a home connection (days at best,
realistically weeks) and write frames to an external drive of at least 2 TB.
Rendering at 0.5 km on a laptop takes minutes per frame, so the full year is
only practical in the cloud. Locally, use a lower `--size` or a shorter period.

## Files

| File | Purpose |
|---|---|
| `get_nc.py` | Find/download the scan nearest a time (anonymous S3) |
| `satpy_frame.py` | satpy true-color renderer |
| `satpy_config/` | Local satpy composite + enhancement (night IR blend) |
| `rgb_frame.py` | Original pipeline: `nctogtiff.py` → resample → `weight.py` → stack → `adjust_image.py` |
| `compare_frames.py` | Side-by-side method comparison |
| `make_year.py` | Resumable batch renderer (local dir or S3) |
| `movie.py` | ffmpeg encoder |
| `goes17_lut.json`, `GOES17_color_template.png` | Color LUT and the reference image it was fitted to (legacy method) |
