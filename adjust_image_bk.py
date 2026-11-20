
import numpy as np
import os
import cv2
from skimage.exposure import cumulative_distribution
import json


def main(in_tif, outfile=None, alpha=2.0, beta=12000, w=5424, h=5424):
    if outfile is None:
        in_ext = os.path.splitext(in_tif)[1]
        outfile = in_tif.replace(in_ext, ".png")

    image = cv2.imread(in_tif, cv2.IMREAD_UNCHANGED)
    dim = (w, h)
    image = cv2.resize(image, dim, interpolation=cv2.INTER_AREA)

    buf = cv2.addWeighted(image, alpha, image, 0, beta)

    if os.path.splitext(outfile)[1] == '.jpg':
        buf_8bit = cv2.convertScaleAbs(buf, alpha=255/buf.max())
        cv2.imwrite(outfile, buf_8bit, [cv2.IMWRITE_JPEG_QUALITY, 98])
    else:
        cv2.imwrite(outfile, buf)
    return outfile




def cdf(im):
    '''
    computes the CDF of an image im as 2D numpy ndarray
    '''
    c, b = cumulative_distribution(im) 
    # pad the beginning and ending pixels and their CDF values
    c = np.insert(c, 0, [0]*b[0])
    c = np.append(c, [1]*(255-b[-1]))
    return c

def hist_matching(c, c_t, im):
    '''
    c: CDF of input image computed with the function cdf()
    c_t: CDF of template image computed with the function cdf()
    im: input image as 2D numpy ndarray
    returns the modified pixel values
    ''' 
    pixels = np.arange(256)
    # find closest pixel-matches corresponding to the CDF of the input image, given the value of the CDF H of   
    # the template image at the corresponding pixels, s.t. c_t = H(pixels) <=> pixels = H-1(c_t)
    new_pixels = np.interp(c, c_t, pixels) 
    im = (np.reshape(new_pixels[im.ravel()], im.shape)).astype(np.uint8)
    return im

def image_to_random_vec(image, nsamp=1000):
    np.random.seed(231)
    xx=np.random.choice(image.shape[0], size=nsamp, replace=True)
    yy=np.random.choice(image.shape[1], size=nsamp, replace=True)
    rvec=image[xx,yy].flatten()
    return rvec


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)

if __name__ == "__main__":
    in_tif = "/Users/jetolan/goes/tmp/tiff/OR_ABI-L1b-RadF-M6C02_G17_s20212561700321_e20212561709388_c20212561709417resampledstack.tiff"
    in_tif = "/Users/jetolan/data/goes/tmp/tiff/OR_ABI-L1b-RadF-M6C02_G17_s20211641950321_e20211641959388_c20211641959421resampledstack.tiff"
    #main(in_tif)

    in_tif = "/Users/jetolan/data/goes/tmp/tiff/OR_ABI-L1b-RadF-M6C02_G17_s20211641950321_e20211641959388_c20211641959421resampledstack.tiff"
    template="/Users/jetolan/Desktop/GEOS17_color_template.png"
    import matplotlib.pyplot as plt
    from skimage.exposure import match_histograms

    im = cv2.imread(in_tif, cv2.IMREAD_UNCHANGED)
    im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
    dim = (5424//4, 5424//4)
    im = cv2.convertScaleAbs(im, alpha=255/im.max())
    im = cv2.resize(im, dim, interpolation=cv2.INTER_AREA)
    
    temp = cv2.imread(template, cv2.IMREAD_UNCHANGED)
    temp = cv2.cvtColor(temp, cv2.COLOR_BGR2RGB)
    temp = cv2.convertScaleAbs(temp, alpha=255/temp.max())
    temp = cv2.resize(temp, dim, interpolation=cv2.INTER_AREA)
    
    
    out = match_histograms(im, temp, channel_axis=2)
    #out = cv2.convertScaleAbs(out, alpha=255/out.max())



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
    goes_lut_file='goes17_lut.json'
    with open(goes_lut_file, 'w') as dst:
        json_dump=json.dumps({'lut':lut.tolist()}, cls=NumpyEncoder)
        dst.write(json_dump)

    #open pre saved lut json
    with open(goes_lut_file) as src:
        json_load = json.load(src)
        lutr = np.asarray(json_load["lut"])

    out2=cv2.LUT(im, lut)
    """
    image = cv2.imread(in_tif, cv2.IMREAD_UNCHANGED)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    dim = (5424//2, 5424//2)
    image = cv2.resize(image, dim, interpolation=cv2.INTER_AREA)
    image_8bit = cv2.convertScaleAbs(image, alpha=255/image.max())
    lab = cv2.cvtColor(image_8bit, cv2.COLOR_RGB2LAB).astype('float32')

    temp = cv2.imread(template, cv2.IMREAD_UNCHANGED)
    temp = cv2.cvtColor(temp, cv2.COLOR_BGR2RGB)
    tlab = cv2.cvtColor(temp, cv2.COLOR_RGB2LAB).astype('float32')

    from skimage.io import imread
    #L = cv2.imread('/Users/jetolan/Desktop/rocksA.png')
    #L = cv2.imread(template, cv2.IMREAD_UNCHANGED)
    #L = cv2.cvtColor(L, cv2.COLOR_BGR2RGB)
     
    L = cv2.imread(in_tif, cv2.IMREAD_UNCHANGED)
    L = cv2.cvtColor(L, cv2.COLOR_BGR2RGB)
    dim = (5424//4, 5424//4)
    L = cv2.resize(L, dim, interpolation=cv2.INTER_AREA)
    L = cv2.convertScaleAbs(L, alpha=255/L.max())
    #L = cv2.cvtColor(L, cv2.COLOR_RGB2LAB)
    
    #R = cv2.imread('/Users/jetolan/Desktop/rocksB.png')
    R = cv2.imread(template, cv2.IMREAD_UNCHANGED)
    #R = cv2.cvtColor(L, cv2.COLOR_RGB2LAB)
    
    from skimage.exposure import match_histograms
    out=match_histograms(L, R, channel_axis=2)

    #out=cv2.cvtColor(out.astype("uint8"), cv2.COLOR_LAB2RGB)
    #result = np.hstack((out,R))
    #before = np.hstack((L,R))
    #out=match_histograms(lab, tlab, channel_axis=2)
    
    out = np.zeros(image.shape)
    for ii, _ in enumerate(["L","A", "B"]):
        vlab = image_to_random_vec(lab[...,ii]) 
        vtlab = image_to_random_vec(tlab[...,ii])
        c = cdf(vlab)
        c_t = cdf(vtlab)
        out[...,ii] = hist_matching(c,c_t, lab[...,ii])
        vout = image_to_random_vec(out[...,ii])
        c_o=cdf(vout.astype('uint8'))
        plt.figure()
        plt.plot(c_o)
        plt.plot(c_t,'r')
        plt.plot(c,'g')
        plt.show()
    """
    #outc=cv2.cvtColor(out.astype("uint8"), cv2.COLOR_LAB2RGB)

