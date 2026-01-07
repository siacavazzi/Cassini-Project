# -*- coding: utf-8 -*-
"""
Created on Sat Apr  9 13:09:54 2022

@author: Sam I
"""

import numpy as np
from skimage.io import imread, imsave
from skimage import img_as_ubyte, img_as_uint, img_as_float
from skimage.exposure import match_histograms
import warnings

#from color_transfer import color_transfer

import cv2

last = None



def align_images(imgs):
    ref = imgs[0] # set first image as reference
    for i in range(1, len(imgs)):
        imgs[i] = imgAlign(ref,imgs[i], False)
        
    return imgs
        
        
def seqAlign(im):
    global last
    if last is None:
        last = im
        return im
    try:
        
        out = imgAlign(last,im)
        last = out
        return out
    except:
        return
    
    
def match_hist(im1, im2):
    return match_histograms(im2, im1)


def find_edges(gray_img):
    height, width = gray_img.shape
    gray_img = 255 - gray_img
    gray_img[gray_img > 100] = 255
    gray_img[gray_img <= 100] = 0
    black_padding = np.zeros((50, width))
    gray_img = np.row_stack((black_padding, gray_img))
    kernel = np.ones((30, 30), np.uint8)
    closing = cv2.morphologyEx(gray_img, cv2.MORPH_CLOSE, kernel)
    edges = cv2.Canny(closing, 100, 200)
    
    return edges
    
    
def imgAlign(im1, im2, mosaic):
    mosaic = True
    try:
        # Convert images to grayscale
        im1_gray = cv2.cvtColor(im1,cv2.COLOR_BGR2GRAY)
        im2_gray = cv2.cvtColor(im2,cv2.COLOR_BGR2GRAY)
        #warp_mode = cv2.MOTION_HOMOGRAPHY
    
        if mosaic:
            warp_mode = cv2.MOTION_HOMOGRAPHY
            im1_gray = find_edges(im1_gray)
            im2_gray = find_edges(im2_gray)
            
            """
            im1_gray = cv2.GaussianBlur(im1_gray, (3,3), 0)
            im2_gray = cv2.GaussianBlur(im2_gray, (3,3), 0)
    
            im1_gray = cv2.Canny(image=im1_gray, threshold1=200, threshold2=200)
            im2_gray = cv2.Canny(image=im2_gray, threshold1=200, threshold2=200)
            
            """      
        # Find size of image1
        sz = im1.shape

    # Define the motion model
  

    # Define 2x3 or 3x3 matrices and initialize the matrix to identity
        if warp_mode == cv2.MOTION_HOMOGRAPHY :
            warp_matrix = np.eye(3, 3, dtype=np.float32)
        else :
            warp_matrix = np.eye(2, 3, dtype=np.float32)

    # Specify the number of iterations.
        number_of_iterations = 2000;

    # Specify the threshold of the increment
    # in the correlation coefficient between two iterations
        termination_eps = 0.1;

    # Define termination criteria
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, number_of_iterations,  termination_eps)

    # Run the ECC algorithm. The results are stored in warp_matrix.
        (cc, warp_matrix) = cv2.findTransformECC (im1_gray,im2_gray,warp_matrix, warp_mode, criteria)

        if warp_mode == cv2.MOTION_HOMOGRAPHY :
            # Use warpPerspective for Homography
            im2_aligned = cv2.warpPerspective (im2, warp_matrix, (sz[1],sz[0]), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP)
        else :
            # Use warpAffine for Translation, Euclidean and Affine
            im2_aligned = cv2.warpAffine(im2, warp_matrix, (sz[1],sz[0]), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP);

        return im2_aligned
    
    except:
        return im2
    
def calc_brightness(image, sigma=4):
        mask = np.ones_like(image[:, :], dtype=bool)
    
        if sigma is not None:
            mean = np.mean(image[:, :])
            std = np.std(image[:, :])
            dist = np.abs(image[:, :] - mean) / std
            mask[dist > sigma] = False

        return np.mean(image[mask])
    
def scale_brightness(image, scale):
    
        adjusted_image = scale * img_as_float(image)
        adjusted_image[adjusted_image >= 1.0] = 1.0
    
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', category=UserWarning)
            if image.dtype == np.dtype('uint8'):
                adjusted_image = img_as_ubyte(adjusted_image)
            elif image.dtype == np.dtype('uint16'):
                adjusted_image = img_as_uint(adjusted_image)

        return adjusted_image

class img_deflicker:
    
    def __init__(self):
        self.mean = []


    def compute_avg(self):
        avg = 0
        for i in range(0,len(self.mean)):
            avg = avg + self.mean[i]
           
        avg = avg / len(self.mean)    
        print("AVERAGE:::: ")
        print(avg)
        return avg
            
    
    def rolling_avg_deflicker(self, image, rolling_avg=10):
        
        if len(self.mean) >= rolling_avg:
            self.mean.pop(0)
            brightness = calc_brightness(image)
            self.mean.append(brightness)
            
            scale = self.compute_avg() / brightness
            
            return scale_brightness(image,scale)
        
        if len(self.mean) < rolling_avg:
            self.mean.append(calc_brightness(image))
            return image
    
    



def image_stats(image):
    # Compute the mean and standard deviation of each channel
    (l, a, b) = cv2.split(image)
    (l_mean, l_std) = (l.mean(), l.std())
    (a_mean, a_std) = (a.mean(), a.std())
    (b_mean, b_std) = (b.mean(), b.std())

    # return the color statistics
    return (l_mean, l_std, a_mean, a_std, b_mean, b_std)


def transfer_with_alpha(source, target):
    alpha = cv2.split(source)[3]
    output = match_hist(source, target)
    
    output = cv2.cvtColor(output, cv2.COLOR_RGB2RGBA)
    output[:, :, 3] = alpha
    return output
























# This function will perform color transfer from one input image (source)
# onto another input image (destination)
def color_transfer(source, target, clip=True, preserve_paper=False):
	"""
	Transfers the color distribution from the source to the target
	image using the mean and standard deviations of the L*a*b*
	color space.
	This implementation is (loosely) based on to the "Color Transfer
	between Images" paper by Reinhard et al., 2001.
	Parameters:
	-------
	source: NumPy array
		OpenCV image in BGR color space (the source image)
	target: NumPy array
		OpenCV image in BGR color space (the target image)
	clip: Should components of L*a*b* image be scaled by np.clip before 
		converting back to BGR color space?
		If False then components will be min-max scaled appropriately.
		Clipping will keep target image brightness truer to the input.
		Scaling will adjust image brightness to avoid washed out portions
		in the resulting color transfer that can be caused by clipping.
	preserve_paper: Should color transfer strictly follow methodology
		layed out in original paper? The method does not always produce
		aesthetically pleasing results.
		If False then L*a*b* components will scaled using the reciprocal of
		the scaling factor proposed in the paper.  This method seems to produce
		more consistently aesthetically pleasing results 
	Returns:
	-------
	transfer: NumPy array
		OpenCV image (w, h, 3) NumPy array (uint8)
	"""
	# convert the images from the RGB to L*ab* color space, being
	# sure to utilizing the floating point data type (note: OpenCV
	# expects floats to be 32-bit, so use that instead of 64-bit)
 
	source = cv2.cvtColor(source, cv2.COLOR_BGR2LAB).astype("float32")
	target = cv2.cvtColor(target, cv2.COLOR_BGR2LAB).astype("float32")

	# compute color statistics for the source and target images
	(lMeanSrc, lStdSrc, aMeanSrc, aStdSrc, bMeanSrc, bStdSrc) = image_stats(source)
	(lMeanTar, lStdTar, aMeanTar, aStdTar, bMeanTar, bStdTar) = image_stats(target)

	# subtract the means from the target image
	(l, a, b) = cv2.split(target)
	l -= lMeanTar
	a -= aMeanTar
	b -= bMeanTar

	if preserve_paper:
		# scale by the standard deviations using paper proposed factor
		l = (lStdTar / lStdSrc) * l
		a = (aStdTar / aStdSrc) * a
		b = (bStdTar / bStdSrc) * b
	else:
		# scale by the standard deviations using reciprocal of paper proposed factor
		l = (lStdSrc / lStdTar) * l
		a = (aStdSrc / aStdTar) * a
		b = (bStdSrc / bStdTar) * b

	# add in the source mean
	l += lMeanSrc
	a += aMeanSrc
	b += bMeanSrc

	# clip/scale the pixel intensities to [0, 255] if they fall
	# outside this range
	l = _scale_array(l, clip=clip)
	a = _scale_array(a, clip=clip)
	b = _scale_array(b, clip=clip)

	# merge the channels together and convert back to the RGB color
	# space, being sure to utilize the 8-bit unsigned integer data
	# type
	transfer = cv2.merge([l, a, b])
	transfer = cv2.cvtColor(transfer.astype("uint8"), cv2.COLOR_LAB2BGR)
	
	# return the color transferred image
	return transfer

def image_stats(image):
	"""
	Parameters:
	-------
	image: NumPy array
		OpenCV image in L*a*b* color space
	Returns:
	-------
	Tuple of mean and standard deviations for the L*, a*, and b*
	channels, respectively
	"""
	# compute the mean and standard deviation of each channel
	(l, a, b) = cv2.split(image)
	(lMean, lStd) = (l.mean(), l.std())
	(aMean, aStd) = (a.mean(), a.std())
	(bMean, bStd) = (b.mean(), b.std())

	# return the color statistics
	return (lMean, lStd, aMean, aStd, bMean, bStd)

def _min_max_scale(arr, new_range=(0, 255)):
	"""
	Perform min-max scaling to a NumPy array
	Parameters:
	-------
	arr: NumPy array to be scaled to [new_min, new_max] range
	new_range: tuple of form (min, max) specifying range of
		transformed array
	Returns:
	-------
	NumPy array that has been scaled to be in
	[new_range[0], new_range[1]] range
	"""
	# get array's current min and max
	mn = arr.min()
	mx = arr.max()

	# check if scaling needs to be done to be in new_range
	if mn < new_range[0] or mx > new_range[1]:
		# perform min-max scaling
		scaled = (new_range[1] - new_range[0]) * (arr - mn) / (mx - mn) + new_range[0]
	else:
		# return array if already in range
		scaled = arr

	return scaled

def _scale_array(arr, clip=True):
	"""
	Trim NumPy array values to be in [0, 255] range with option of
	clipping or scaling.
	Parameters:
	-------
	arr: array to be trimmed to [0, 255] range
	clip: should array be scaled by np.clip? if False then input
		array will be min-max scaled to range
		[max([arr.min(), 0]), min([arr.max(), 255])]
	Returns:
	-------
	NumPy array that has been scaled to be in [0, 255] range
	"""
	if clip:
		scaled = np.clip(arr, 0, 255)
	else:
		scale_range = (max([arr.min(), 0]), min([arr.max(), 255]))
		scaled = _min_max_scale(arr, new_range=scale_range)

	return scaled






























