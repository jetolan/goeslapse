"""True-colour full-disk frame using satpy.

Synthetic green and Rayleigh (atmospheric haze) correction are done by
satpy/pyspectral. Optionally blends a C13 infrared image into the night side.
"""
import os
import shutil

import pandas as pd

import get_nc

# make our local composites (satpy_config/composites/abi.yaml) visible to satpy
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault('SATPY_CONFIG_PATH', os.path.join(HERE, 'satpy_config'))

# composite name -> ABI channels it needs
COMPOSITES = {
    'true_color': (1, 2, 3),
    'true_color_with_night_ir_nobg': (1, 2, 3, 13),
    'true_color_soft': (1, 2, 3),
    'true_color_soft_wide': (1, 2, 3),
}


def download(date, sat, frame, bands, work_dir):
    return [get_nc.main(sat, b, frame, date, local_dir=work_dir) for b in bands]


def render(files, out_file, composite='true_color', resolution='finest',
           size=None):
    """Render `composite` from local ABI L1b files and write `out_file`.

    resolution: 'finest' (0.5 km, 21696 px) or 'coarsest' (1 km/2 km).
    size: optional final square pixel size (area-averaged downscale).
    """
    from satpy import Scene
    from satpy.enhancements.enhancer import get_enhanced_image

    scn = Scene(reader='abi_l1b', filenames=files)
    scn.load([composite])
    area = scn.finest_area() if resolution == 'finest' else scn.coarsest_area()
    lcl = scn.resample(area, resampler='native')
    if size is not None and size != area.width:
        if area.width % size:
            raise ValueError(f'size {size} must divide grid width {area.width}')
        factor = area.width // size
        lcl = lcl.aggregate(x=factor, y=factor)
    img = get_enhanced_image(lcl[composite])
    os.makedirs(os.path.dirname(out_file) or '.', exist_ok=True)
    save_kwargs = {'quality': 95} if out_file.endswith('.jpg') else {}
    img.save(out_file, fill_value=0, **save_kwargs)
    return out_file


def main(date, sat, frame, out_dir, composite='true_color',
         resolution='finest', size=None, work_dir=None, clean=True):
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(
        out_dir, f"{sat}_{pd.to_datetime(date):%Y%m%dT%H%M}.jpg")
    if os.path.exists(out_file):
        return out_file
    if work_dir is None:
        work_dir = os.path.join(out_dir, 'tmp')
    files = download(date, sat, frame, COMPOSITES[composite], work_dir)
    render(files, out_file, composite, resolution, size)
    if clean:
        shutil.rmtree(work_dir, ignore_errors=True)
    return out_file
