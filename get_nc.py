import boto3
import os
import pandas as pd
from datetime import datetime
import numpy as np


def convert_date(date_str):
    pddate = pd.to_datetime(date_str)
    doy = pddate.timetuple().tm_yday
    year = pddate.year
    hour = pddate.hour
    minute = pddate.minute
    return year, doy, hour, minute


def prefix(frame, band, sat, year, doy, hour, minute=None):
    """
    frame: "F" full disk
    sat: "G17" or "G16"
    band: 1 blue
          2 red
          3 nir
    """
    doy_str = str(doy).zfill(3)
    hour_str = str(hour).zfill(2)
    minute_str = str(minute).zfill(2)

    base = f"ABI-L1b-Rad{frame}/{year}/{doy_str}/{hour_str}/"

    # there appears to be some naming convention changes
    if year >= 2019:
        mm = "M6"
    else:
        mm = "M3"

    if minute:
        filename = f"OR_ABI-L1b-Rad{frame}-{mm}C0{band}_{sat}_s{year}{doy_str}{hour_str}{minute_str}"
    else:
        filename = f"OR_ABI-L1b-Rad{frame}-{mm}C0{band}_{sat}_s{year}{doy_str}{hour_str}"

    prefix = f"{base}{filename}"
    return prefix


def aws_ls(bucket, prefix):
    s3_client = boto3.client('s3')
    contents = s3_client.list_objects(Bucket=bucket, Prefix=prefix)['Contents']
    files = [c['Key'] for c in contents]
    return files


def parse_nc_fname(fname):
    ind = fname.find('_s')
    date = fname[ind+2:ind+15]
    dd = pd.to_datetime(date, format='%Y%j%H%M%S')
    return dd


def aws_get(bucket, target_file, local_dir='/tmp', replace=False, outfile=None):
    s3_client = boto3.client('s3')
    if outfile is None:
        outfile = f"{local_dir}/{target_file.split('/')[-1]}"
    if os.path.exists(outfile) and not replace:
        print(f'{outfile} exists and replace = False, skipping download')
    else:
        print(f'Downloading to {outfile}...')
        s3_client.download_file(bucket, target_file, outfile)
    return outfile


def main(sat, band, frame, date, local_dir='/tmp', dryrun=False, replace=False):
    '''
    dryrun: bool
            If true, will return output filename but not download
    '''
    sat_dict = {'goes17': 'G17', 'goes16': 'G16'}
    short_sat = sat_dict[sat]
    aws_bucket = f'noaa-{sat}'
    year, doy, hour, minute = convert_date(date)
    prefix_hourly = prefix(frame, band, short_sat, year, doy, hour)
    aws_candidates = aws_ls(aws_bucket, prefix_hourly)
    obs_dates = [parse_nc_fname(r) for r in aws_candidates]
    diff_list = [abs((pd.to_datetime(date)-d).total_seconds())
                 for d in obs_dates]
    print(
        f'Found {sat} observation {np.min(diff_list)} seconds away from {date}')
    ind = np.argmin(diff_list)
    target_file = aws_candidates[ind]
    outfile = f"{local_dir}/{target_file.split('/')[-1]}"
    if not dryrun:
        outfile = aws_get(aws_bucket, target_file,
                          local_dir=local_dir, outfile=outfile, replace=replace)
    return outfile


if __name__ == "__main__":
    date = '2020-09-12 17:00'
    sat = 'goes17'
    band = 1
    frame = 'F'
    local_dir = "/Users/jetolan/goes"

    outfile = main(sat, band, frame, date, local_dir=local_dir)
