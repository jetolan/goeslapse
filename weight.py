#!/usr/bin/env python

import rasterio as rio
from sys import argv
import numpy as np
import riomucho


def weight(ab, window, ij, g):
    ab = np.array(ab).astype(np.float32)
    weighted = (ab[0] * g["weights"][0] + ab[1] * g["weights"][1]) / (
        g["weights"][0] + g["weights"][1]
    )
    return weighted.astype(g["dtype"])

def main(f1, f2, ratio, out):
    """
    ratio:tuple
    """
    
    processes = 4
    g = {"dtype": np.uint16, "weights": list(map(float, ratio))}

    with rio.open(f1) as src:
        windows = [[window, ij] for ij, window in src.block_windows()]
        options = src.profile
        options.update({"count": 1, "compress": "lzw"})

    with riomucho.RioMucho(
            [f1, f2], out, weight,
            windows=windows, global_args=g, options=options) as mucho:
        mucho.run(processes)
    return out
