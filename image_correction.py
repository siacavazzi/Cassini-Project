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



def align_images(imgs, ref=0):
    # ref = index of the frame the others are aligned to; the middle frame in time keeps offsets smallest
    for i in range(0, len(imgs)):
        if i != ref:
            imgs[i] = shift_align(imgs[ref],imgs[i])

    return imgs


"""
Fills a frame's invalid pixels (mask False) from the valid ones around them, so the zeros of
truncated lines don't bleed into neighbouring rows when the frame is shifted or skew its
brightness scale. The pixels stay invalid; this only keeps them from affecting the rest.
"""
def fill_invalid(img, mask):
    if mask.all():
        return img
    return cv2.inpaint(img, (~mask).astype(np.uint8), 3, cv2.INPAINT_TELEA)


"""
Like align_images, but also moves each frame's valid-pixel mask (label.valid_mask) with it,
so pixels a shift leaves uncovered count as invalid too.
Phase correlation needs the frames to look alike; through filters far apart (UV against
IR) it can fail to find a match. A whole target in every frame then still lines up by
its centroid (centroid_shift).
report = optional list that gets one entry per frame: how it was aligned
returns (imgs, masks)
"""
def align_with_masks(imgs, masks, ref=0, report=None):
    for i in range(0, len(imgs)):
        if i == ref:
            if report is not None:
                report.append("reference")
            continue
        shift, how = find_shift(imgs[ref], imgs[i]), "phase"
        if shift is None:
            shift, how = find_shift(edges(imgs[ref]), edges(imgs[i])), "edges"
            # an edge match at exactly no shift is the camera's own fixed pattern (dust rings, bad
            # columns) matching itself, not the target: it says nothing
            if shift is not None and abs(shift[0]) < 0.25 and abs(shift[1]) < 0.25:
                shift = None
        if shift is None:
            shift, how = centroid_shift(imgs[ref], imgs[i]), "centroid"
        if shift is not None:
            imgs[i] = shift_image(imgs[i], *shift)
            masks[i] = shift_image(masks[i].astype(np.float32), *shift) > 0.99
        if report is not None:
            report.append(f"{how} {shift[0]:+.1f},{shift[1]:+.1f}" if shift is not None else "not aligned")
    return imgs, masks


"""
Gradient magnitude of a frame, as a 3 channel 8-bit image for find_shift. Limbs, terminators
and crater rims sit in the same place through every filter even when their brightness does
not (bright haze in blue, dark surface in infrared), so edges can match where the frames don't.
"""
def edges(im):
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) if im.ndim == 3 else im
    gray = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 1.5)
    mag = cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1))
    mag = np.clip(mag * 255.0 / max(np.percentile(mag, 99.5), 1e-6), 0, 255).astype(np.uint8)
    return cv2.cvtColor(mag, cv2.COLOR_GRAY2BGR)


"""
Offset of im2 from im1 by the centroid of the target's lit area, for when phase
correlation fails. Only used when the target sits wholly inside both frames (its lit
area touches no edge), since a cut-off target moves its centroid.
returns (dx, dy) or None
"""
def centroid_shift(im1, im2, max_shift=100):
    centres = []
    for im in (im1, im2):
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32) if im.ndim == 3 else im.astype(np.float32)
        blurred = cv2.GaussianBlur(gray, (0, 0), 3)
        if blurred.max() <= 0:
            return None
        lit = blurred > 0.2 * blurred.max()
        if lit.sum() < 50 or lit[0].any() or lit[-1].any() or lit[:, 0].any() or lit[:, -1].any():
            return None
        ys, xs = np.nonzero(lit)
        weight = blurred[ys, xs]
        centres.append(((xs * weight).sum() / weight.sum(), (ys * weight).sum() / weight.sum()))
    dx, dy = centres[1][0] - centres[0][0], centres[1][1] - centres[0][1]
    if abs(dx) > max_shift or abs(dy) > max_shift:
        return None
    return dx, dy


"""
Finds the sub-pixel translation of im2 relative to im1 by phase correlation.
Filter frames in a color sequence are taken seconds apart, so the target only
moves across the sensor; a translation is the right motion model.
max_shift = largest offset in pixels that is accepted as real
min_response = phase correlation peak below which the match is rejected

returns (dx, dy) or None if no trustworthy match was found
"""
def find_shift(im1, im2, max_shift=100, min_response=0.3):
    im1_gray = cv2.cvtColor(im1,cv2.COLOR_BGR2GRAY).astype(np.float32)
    im2_gray = cv2.cvtColor(im2,cv2.COLOR_BGR2GRAY).astype(np.float32)

    # correlate only the area around the target so empty sky does not dilute the match
    blurred = cv2.GaussianBlur(im1_gray, (0,0), 3)
    ys, xs = np.nonzero(blurred > 0.2 * blurred.max())
    if len(ys) == 0:
        print("Image alignment skipped: blank reference frame")
        return None
    h, w = im1_gray.shape
    y0, y1 = max(ys.min() - max_shift, 0), min(ys.max() + max_shift, h)
    x0, x1 = max(xs.min() - max_shift, 0), min(xs.max() + max_shift, w)
    a = im1_gray[y0:y1, x0:x1]
    b = im2_gray[y0:y1, x0:x1]

    window = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(a, b, window)

    if response < min_response or abs(dx) > max_shift or abs(dy) > max_shift:
        print(f"Image alignment failure: shift ({dx:.1f}, {dy:.1f}) response {response:.2f}")
        return None
    return dx, dy


def shift_image(im, dx, dy):
    h, w = im.shape[:2]
    M = np.float32([[1, 0, -dx], [0, 1, -dy]])
    return cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT)


"""
Aligns im2 to im1; returns im2 unchanged if no trustworthy match was found
"""
def shift_align(im1, im2, max_shift=100, min_response=0.3):
    shift = find_shift(im1, im2, max_shift, min_response)
    if shift is None:
        return im2
    return shift_image(im2, *shift)


"""
Combines repeat exposures of the same filter into one lower-noise frame.
frames = list of images of the same target, filter and exposure time; frames[0] is the reference
sigma = pixels further than this many noise sigmas from the others are rejected
        (cosmic rays, hot pixels)
max_shift = largest offset in pixels between repeats; repeats seconds apart barely move,
        so a bigger offset means a different view or a false match

Each frame is aligned to the reference and brightness-matched to it. Where the scene
itself changed between exposures (a moon moved), a frame is only used where it agrees
with the reference, so moving objects come from the reference alone instead of
leaving ghosts. Frames that cannot be aligned are left out.
returns the stacked frame in the same format as the input (8-bit, 3 channel gray)
"""
"""
Per pixel median of the frames in stack where agrees is True (count = how many per pixel, at
least one), the same as np.nanmedian with the others set to NaN. A sort of the few frames is
several times quicker than nanmedian, which goes through masked arrays.
"""
def agreeing_median(stack, agrees, count):
    ordered = np.sort(np.where(agrees, stack, np.inf), axis=0)
    low = np.take_along_axis(ordered, ((count - 1) // 2)[None], 0)[0]
    high = np.take_along_axis(ordered, (count // 2)[None], 0)[0]
    return (low + high) / 2


def stack_frames(frames, sigma=3.0, max_shift=20):
    ref = frames[0]
    ref_gray = cv2.cvtColor(ref,cv2.COLOR_BGR2GRAY).astype(np.float32)
    blurred = cv2.GaussianBlur(ref_gray, (0,0), 3)
    target = blurred > 0.1 * blurred.max()
    unclipped = target & (ref_gray < 250)

    stack = [ref_gray]
    agrees = [np.ones(ref_gray.shape, bool)]
    for frame in frames[1:]:
        if frame.shape != ref.shape:
            continue
        shift = find_shift(ref, frame, max_shift)
        if shift is None:
            continue
        gray = cv2.cvtColor(shift_image(frame, *shift),cv2.COLOR_BGR2GRAY).astype(np.float32)
        if unclipped.sum() > 100:
            # match brightness to the reference; a gain alone keeps black sky black
            gain = (gray[unclipped] * ref_gray[unclipped]).sum() / max((gray[unclipped] ** 2).sum(), 1)
            gray = gain * gray
        # mark where the scene changed: differences that survive smoothing are structure, not noise
        # (noise is measured over the whole frame, since a moving moon can fill much of the target)
        smooth_diff = cv2.GaussianBlur(gray - ref_gray, (0,0), 2)
        smooth_diff = np.abs(smooth_diff - np.median(smooth_diff))
        noise = 1.4826 * np.median(smooth_diff)
        changed = (smooth_diff > max(5 * noise, 3)).astype(np.uint8)
        # drop specks (cosmic rays, hot pixels are handled per pixel below), then pad what is left
        changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((7,7), np.uint8))
        changed = cv2.dilate(changed, np.ones((15,15), np.uint8)) > 0
        stack.append(gray)
        agrees.append(~changed)

    if len(stack) == 1:
        return ref
    stack = np.array(stack)
    agrees = np.array(agrees)

    # reject single-pixel outliers among the frames that agree with the reference
    count = agrees.sum(axis=0)
    median = agreeing_median(stack, agrees, count)
    resid = np.abs(stack - median)
    noise = 1.4826 * np.median(resid[:, target][agrees[:, target]] if target.any() else resid) + 1
    keep = agrees & (resid <= sigma * noise)
    # with two frames an outlier can't be voted out; keep the darker value,
    # since cosmic rays and hot pixels only ever add light
    pair = (count == 2) & (keep.sum(axis=0) < 2)
    out = (stack * keep).sum(axis=0) / np.maximum(keep.sum(axis=0), 1)
    out = np.where(pair, np.where(agrees, stack, np.inf).min(axis=0), out)
    out = np.where(keep.any(axis=0) | pair, out, ref_gray)

    out = np.clip(out + 0.5, 0, 255).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
        
        
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
    gray_img = np.vstack((black_padding, gray_img))
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






























