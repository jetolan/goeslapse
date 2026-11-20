
import numpy as np
import os
import cv2
from skimage.exposure import cumulative_distribution
import json
from skimage.exposure import match_histograms
from skimage.io import imsave

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LUT = os.path.join(HERE, 'goes17_lut.json')
DEFAULT_TEMPLATE = os.path.join(HERE, 'GOES17_color_template.png')

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)


def create_lut(in_file, template=DEFAULT_TEMPLATE, lut_file=DEFAULT_LUT):
    """
    Note: may be better to use 16bit LUT
    """
    im = cv2.imread(in_file, cv2.IMREAD_UNCHANGED)
    im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
    dim = (5424//4, 5424//4)
    im = cv2.convertScaleAbs(im, alpha=255/im.max())
    im = cv2.resize(im, dim, interpolation=cv2.INTER_AREA)
    
    temp = cv2.imread(template, cv2.IMREAD_UNCHANGED)
    temp = cv2.cvtColor(temp, cv2.COLOR_BGR2RGB)
    temp = cv2.convertScaleAbs(temp, alpha=255/temp.max())
    temp = cv2.resize(temp, dim, interpolation=cv2.INTER_AREA)
    
    out = match_histograms(im, temp, channel_axis=2)

    #make lut
    lut=np.zeros((256,3))
    for band in [0,1,2]:
        for val in range(256):
           x,y=np.where(im[...,band]==val)
           if len(x)>0:
               lut[val,band]=np.mean(temp[x,y,band])
           elif val<255//2:
               lut[val,band]=0
           else:
               lut[val,band]=255
    lut=lut.astype('uint8')
    lut=np.expand_dims(lut, 0)

    #save lut as json
    with open(lut_file, 'w') as dst:
        json_dump=json.dumps({'lut':lut.tolist()}, cls=NumpyEncoder)
        dst.write(json_dump)

    out3= cv2.LUT(im, lut)

    return lut_file

def main(in_file, lut_file=DEFAULT_LUT, out_file=None, w=5424, h=5424):

    if out_file is None:
        in_ext = os.path.splitext(in_file)[1]
        out_file = in_file.replace(in_ext, ".jpg")

    im = cv2.imread(in_file, cv2.IMREAD_UNCHANGED)
    im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)

    dim = (w, h)
    # same 16->8 bit scaling create_lut() used when fitting the LUT
    # (alpha=1.0 clipped nearly every pixel to 255 -> white disk)
    im = cv2.convertScaleAbs(im, alpha=255 / im.max())
    im = cv2.resize(im, dim, interpolation=cv2.INTER_AREA)
    
    #open pre saved lut json
    with open(lut_file) as src:
        json_load = json.load(src)
        lut = np.asarray(json_load["lut"])

    out = cv2.LUT(im, lut)
    
    if os.path.splitext(out_file)[1] == '.jpg':
        imsave(out_file, out.astype('uint8'), quality=98)
    else:
        imsave(out_file, out.astype('uint8'))
    
    return out_file

if __name__ == "__main__":

    in_tif = "/Users/jetolan/data/goes/tmp/tiff/OR_ABI-L1b-RadF-M6C02_G17_s20211641950321_e20211641959388_c20211641959421resampledstack.tiff"
    template="/Users/jetolan/Desktop/GEOS17_color_template.png"

    #lut_file = create_lut(in_tif)
    
    test_tif = "/Users/jetolan/data/goes/tmp/tiff/OR_ABI-L1b-RadF-M6C02_G17_s20211641650321_e20211641659388_c20211641659414resampledstack.tiff"
    outfile = main(test_tif)
   



