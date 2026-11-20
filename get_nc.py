"""Find and download GOES ABI L1b NetCDF files from NOAA's public S3 buckets.

Buckets: s3://noaa-goes16 .. noaa-goes19 (public, us-east-1, anonymous access).
GOES-17 was retired in 2023; GOES-18 is GOES-West and GOES-19 is GOES-East.
"""
import os
from functools import lru_cache

import boto3
import numpy as np
import pandas as pd
from botocore import UNSIGNED
from botocore.config import Config

SAT_SHORT = {'goes16': 'G16', 'goes17': 'G17', 'goes18': 'G18', 'goes19': 'G19'}


@lru_cache(maxsize=None)
def s3_client():
    """Anonymous client: the NOAA buckets are public, no AWS credentials needed."""
    return boto3.client('s3', region_name='us-east-1',
                        config=Config(signature_version=UNSIGNED,
                                      max_pool_connections=32))


def convert_date(date_str):
    pddate = pd.to_datetime(date_str)
    doy = pddate.timetuple().tm_yday
    return pddate.year, doy, pddate.hour, pddate.minute


def hour_prefix(frame, year, doy, hour):
    """S3 key prefix for one hour of a product, e.g. ABI-L1b-RadF/2025/079/21/"""
    return f"ABI-L1b-Rad{frame}/{year}/{doy:03d}/{hour:02d}/"


def band_tag(band):
    """Filename tag for a channel, e.g. 'C02_' (trailing _ so C01 != C010)."""
    return f"C{int(band):02d}_"


def aws_ls(bucket, prefix):
    """List all keys under prefix (paginated; returns [] if none)."""
    paginator = s3_client().get_paginator('list_objects_v2')
    keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(c['Key'] for c in page.get('Contents', []))
    return keys


def parse_nc_fname(fname):
    """Scan start time from an ABI filename (..._sYYYYJJJHHMMSSs_...)."""
    ind = fname.find('_s')
    date = fname[ind + 2:ind + 15]
    return pd.to_datetime(date, format='%Y%j%H%M%S')


def find_key(sat, band, frame, date, max_offset_s=300):
    """S3 key of the scan of `band` whose start is closest to `date`.

    Searches the hour of `date` and the neighbouring hours so that dates near
    an hour boundary still find the right scan. Returns None if nothing is
    within max_offset_s seconds.
    """
    date = pd.to_datetime(date)
    if date.tzinfo is not None:
        date = date.tz_convert('UTC').tz_localize(None)
    bucket = f'noaa-{sat}'
    tag = band_tag(band)
    candidates = []
    for hh in (date - pd.Timedelta(hours=1), date, date + pd.Timedelta(hours=1)):
        year, doy, hour, _ = convert_date(hh)
        candidates += [k for k in aws_ls(bucket, hour_prefix(frame, year, doy, hour))
                       if tag in k and f'_{SAT_SHORT[sat]}_' in k]
    if not candidates:
        return None
    diffs = np.array([abs((date - parse_nc_fname(k)).total_seconds())
                      for k in candidates])
    ind = int(np.argmin(diffs))
    if diffs[ind] > max_offset_s:
        return None
    return candidates[ind]


def aws_get(bucket, key, local_dir='/tmp', replace=False, outfile=None):
    if outfile is None:
        outfile = os.path.join(local_dir, os.path.basename(key))
    os.makedirs(os.path.dirname(outfile) or '.', exist_ok=True)
    if os.path.exists(outfile) and not replace:
        print(f'{outfile} exists and replace = False, skipping download')
        return outfile
    print(f'Downloading s3://{bucket}/{key} ...')
    tmp = outfile + '.part'
    s3_client().download_file(bucket, key, tmp)
    os.replace(tmp, outfile)
    return outfile


def main(sat, band, frame, date, local_dir='/tmp', dryrun=False, replace=False):
    """Download the scan of `band` nearest `date`; return the local path.

    dryrun: return the would-be local path without downloading.
    Raises FileNotFoundError if no scan is within 5 minutes of `date`.
    """
    key = find_key(sat, band, frame, date)
    if key is None:
        raise FileNotFoundError(f'No {sat} C{band:02d} {frame} scan near {date}')
    print(f'Found {sat} scan {parse_nc_fname(key)} for {date}')
    outfile = os.path.join(local_dir, os.path.basename(key))
    if not dryrun:
        outfile = aws_get(f'noaa-{sat}', key, outfile=outfile, replace=replace)
    return outfile


if __name__ == "__main__":
    outfile = main('goes18', 1, 'F', '2025-03-20 21:10', local_dir='/tmp/goes')
    print(outfile)
