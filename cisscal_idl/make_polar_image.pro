;---------------------
; make_polar_image.pro
;---------------------
;
;Prior to using make_polar_image the user should be familiar with the
;expected uncertainty in the final product by consulting the ISS final
;calibration report submitted to a professional journal in 2019
;(Knowles first author).
;
;This function ingests registered or unregistered, calibrated,
;polarized images from the Cassini ISS cameras. Input images must be
;in VICAR format, and specified in sets of two or three, with filters 
;consisting of either: 
;   1) P0, P60 and P120 (NAC)
;   2) IRP0 and IRP90 (WAC)
;   3) CLR and IRP0 (NAC and WAC)
;with matching colors (except for CLR) in the opposite filter
;position. The order of input images is irrelevant, only that they
;constitute a matching set. The input images must be taken close
;together in time because any variation in image scale or orientation
;will produce errors. Variation among the images in the line, sample
;location of the target can be corrected with the align option. 
;
;The code includes the transmissions parallel and perpendicular to
;the polarizing axis of the polarizer, derived from observations.
;These are functions of wavelength, and different passbands have
;different effective parallel and perpendicular transmissions. 
;
;As of June 2019, all filter/polarizer combinations are supported
;except for those with the CLR filter in the opposite filter wheel.
;
;The returned value is a structure defined as follows:
; 
;If input is two file names (files containing either [IRP0, IRP90] or
;[IRP0, CLR]) the function returns intensity I (same units as the
;original, and indicated by the tag name "intensity") and the Stokes
;parameter Q/I (range -1 to +1) defined with respect to the direction
;of the principal axis of IRP0 (tag name: "Q").
;
;If input is three files (containing P0, P60, P120) the returned
;structure contains intensity, polarization (from 0.0 to 1.0 tag
;name: "polarization"), and theta, the angle of the electric vector
;relative to the camera Y axis (+/- 90 degrees tag name: "theta").
;
;For more information on the polarization code implementation, see the ISS
;Data User's Guide, the latest version of which can be obtained at:
;
;   http://pds-imaging.jpl.nasa.gov/software/
;
;Keywords:
;
;  Set the /align keyword to co-register the images if they have
;   not already been co-registered.
;  Set the /flip keyword to flip the output arrays about the x
;   (sample) axis
;  Set the /silent keyword to suppress warning and info messages (but 
;   not error messages).
;  Set the outfile keyword equal to the filename of a VICAR-format
;   file containing the calculated intensity. This file will be given
;   the same label as file1 to track calibration history.
;  Transmission coefficients for the [polarizers are returned if Tvals is set
;
;Invoking the program:
;
;  result = make_polar_image(file1,file2,[file3],[/align],[/flip],$
;          [outfile=outfile],[silent=silent])
;
;Written by Bob West and Ben Knowles
;
;  version 1.0, May 25, 2001
; 
;  version 2.0, October 31, 2002 - uses filter derived t_parallel and
;       t_perp from polarization_package.
;
;  version 3.0, January, 2006 - still needs an absolute calibration factor
;       for the intensity calculation.
;
;  version 4.0, November 2007, various revisions by B. Knowles.
;
;  version 5.0, December 7 2007, converted image input to file input,
;       instituted automatic detection of filter, polarizers,
;       Vis/IR, created structure output.
;
;  version 6.0, August 20, 2013, Cleaned up and incorporated into
;       CISSCAL by B. Knowles.
;
;  version 7.0, March 14, 2014, No longer assumes T_parallel and T_perpendiular
;       are the same for all polarizersupdates T_parallel and T_perpendicular
;       based on POLCAL calibration results for some filters.  New
;       algorithm by R. West.
;
;  version 8.0, April 23, 2014, Improved error handling and cleaned up
;       for CISSCAL 3.7 by B. Knowles.
;
;  version 9.0, November 20, 2014, Additional small bug fixes by
;       B. Knowles.
;
;  version 10.0, June 25, 2019, Added remaining filters in opposite
;       filter wheels and revised transmission constants by R. West.
;
;  version 11.0, June 28, 2019, various cleanup by B. Knowles.
;
;  version 12.0, August 2, 2019, New transmision valus by R. West.



pro mpi_calc_ipt,I0,I60,I120,T1,T2,d,I,Pol,Theta

; To calculate Intensity, Polarization, Theta from measurements in
; three polarizers, and with known transmissions T1 and T2 (Parallel 
; and Perpendicular to the electric vector)
;
; The extra parameter d is if polarizer 0 has extra transmittance of 
; both polarizations such that
;   T1(P0) = T1 + d; T2(P0) = T2 + d.  
;
; On return, I is in the same units as I0, Pol is from 0 to 1, Theta 
; is in degrees

z = I0
s = I60
n = I120
o = T1
w = T2

U1 = (6*(o - w)*(2*d*(n + s) + (o + w)*(n + s - 2*z))*(n + s + z) - $
      4*Sqrt(3)*Sqrt((2*d*(n + s) + (o + w)*(n + s - 2*z))^2*$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 + s^2 - s*z + z^2 - n*(s + z)))))/$
      (3*(o - w)*(2*d + 3*(o + w))*(2*d*(n + s) + (o + w)*(n + s - 2*z)))

P1 = (4*Sqrt((2*d*(n + s) + (o + w)*(n + s - 2*z))^2*$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 + s^2 - s*z + z^2 - n*(s + z)))))/$
      (Sqrt(3)*(o - w)*(2*d + 3*(o + w))*(2*d*(n + s) + (o + w)*(n + s - 2*z)))

Theta1 = ATAN(-Sqrt((24*d^2*(n^2 + n*s + s^2) + 36*d*(o + w)*$
      (n^2 + s^2 - (n + s)*z) + 18*(o + w)^2*(n^2 + s^2 - s*z + z^2 - $
      n*(s + z)) - 3*Sqrt(3)*Sqrt((2*d*(n + s) + (o + w)*(n + s - 2*z))^2*$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 - n*s + s^2 - (n + s)*z + z^2))))/$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 - n*s + s^2 - (n + s)*z + z^2))), $
      (Sqrt((8*d^2*(n^2 + n*s + s^2) + 12*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      6*(o + w)^2*(n^2 + s^2 - s*z + z^2 - n*(s + z)) - $
      Sqrt(3)*Sqrt((2*d*(n + s) + (o + w)*(n + s - 2*z))^2*$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 - n*s + s^2 - (n + s)*z + z^2))))/$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 - n*s + s^2 - (n + s)*z + z^2)))*$
      (3*(2*d*(n + s) + (o + w)*(n + s - 2*z))^2 + $
      2*Sqrt(3)*Sqrt((2*d*(n + s) + (o + w)*(n + s - 2*z))^2*$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 - n*s + s^2 - (n + s)*z + z^2)))))/$
      ((n - s)*(2*d + 3*(o + w))*(2*d*(n + s) + (o + w)*(n + s - 2*z))))

U3 = (6*(o - w)*(2*d*(n + s) + (o + w)*(n + s - 2*z))*(n + s + z) + $
      4*Sqrt(3)*Sqrt((2*d*(n + s) + (o + w)*(n + s - 2*z))^2*$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 + s^2 - s*z + z^2 - n*(s + z)))))/$
      (3*(o - w)*(2*d + 3*(o + w))*(2*d*(n + s) + (o + w)*(n + s - 2*z)))
 
P3 = (-4*Sqrt((2*d*(n + s) + (o + w)*(n + s - 2*z))^2*$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 + s^2 - s*z + z^2 - n*(s + z)))))/$
      (Sqrt(3)*(o - w)*(2*d + 3*(o + w))*(2*d*(n + s) + (o + w)*(n + s - 2*z)))
 
Theta3 = ATAN(-(Sqrt(3)*Sqrt((8*d^2*(n^2 + n*s + s^2) + 12*d*(o + w)*$
      (n^2 + s^2 - (n + s)*z) + 6*(o + w)^2*(n^2 + s^2 - s*z + z^2 - $
      n*(s + z)) + Sqrt(3)*Sqrt((2*d*(n + s) + (o + w)*(n + s - 2*z))^2*$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 - n*s + s^2 - (n + s)*z + z^2))))/$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 - n*s + s^2 - (n + s)*z + z^2)))), $
      ((3*(2*d*(n + s) + (o + w)*(n + s - 2*z))^2 - $
      2*Sqrt(3)*Sqrt((2*d*(n + s) + (o + w)*(n + s - 2*z))^2*$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 - n*s + s^2 - (n + s)*z + z^2))))*$
      Sqrt((8*d^2*(n^2 + n*s + s^2) + 12*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      6*(o + w)^2*(n^2 + s^2 - s*z + z^2 - n*(s + z)) + $
      Sqrt(3)*Sqrt((2*d*(n + s) + (o + w)*(n + s - 2*z))^2*$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 - n*s + s^2 - (n + s)*z + z^2))))/$
      (4*d^2*(n^2 + n*s + s^2) + 6*d*(o + w)*(n^2 + s^2 - (n + s)*z) + $
      3*(o + w)^2*(n^2 - n*s + s^2 - (n + s)*z + z^2))))/$
      ((n - s)*(2*d + 3*(o + w))*(2*d*(n + s) + (o + w)*(n + s - 2*z))))

I1 = U1 + P1
Pol1 = -p1/I1
theta1 = -theta1*180./!pi       ; Note: May need to change the sign

I3 = U3 + P3
Pol3 = -p3/I3
theta3 = -theta3*180./!pi       ; Note: May need to change the sign

angle = theta1*!Pi/180.
iu = u1
ip = p1
izero1 = iu*(t1 + t2 + 2.*d)/2 + ip*(cos(angle)*cos(angle)*(t1+d) + $
                                     sin(angle)*sin(angle)*(t2+d))
isixty1 = iu*(t1 + t2)/2 + ip*(cos(angle-!Pi/3)*cos(angle-!Pi/3)*(t1) + $
                               sin(angle-!pi/3)*sin(angle-!Pi/3)*(t2))
ionetwenty1 = iu*(t1 + t2)/2 + ip*(cos(angle-2*!Pi/3)*cos(angle-2*!Pi/3)*(t1) + $
                                   sin(angle-2*!pi/3)*sin(angle-2*!pi/3)*(t2))

diff1 = (izero1-i0)^2 + (isixty1-i60)^2 + (ionetwenty1-i120)^2

angle = theta3*!Pi/180.
iu = u3
ip = p3
izero3 = iu*(t1 + t2 + 2.*d)/2 + ip*(cos(angle)*cos(angle)*(t1+d) + $
                                     sin(angle)*sin(angle)*(t2+d))
isixty3 = iu*(t1 + t2)/2 + ip*(cos(angle-!Pi/3)*cos(angle-!Pi/3)*(t1) + $
                               sin(angle-!pi/3)*sin(angle-!Pi/3)*(t2))
ionetwenty3 = iu*(t1 + t2)/2 + ip*(cos(angle-2*!Pi/3)*cos(angle-2*!Pi/3)*(t1) + $
                                   sin(angle-2*!pi/3)*sin(angle-2*!pi/3)*(t2))

diff3 = (izero3-i0)^2 + (isixty3-i60)^2 + (ionetwenty3-i120)^2

good = where(pol3 ge 0)
;good = where(diff3 lt diff1 and pol3 ge 0.)

i = i1
pol = pol1
theta = theta1
if total(good) gt 0 then begin
   i[good] = i3[good]
   pol[good] = pol3[good]
   theta[good] = theta3[good]
endif

if not min(finite(i)) then begin
; try to fix some NANs by replacing by a finite value that can be flagged later
   b = finite(i)
   bad = where(b eq 0)
   i(bad) = 1000.
   if n_elements(i) gt 10000 then begin
      filtered = median(i,7)
      if n_elements(bad)/float(n_elements(i)) lt 0.1 then i(bad) = filtered(bad)
   endif
endif

if not min(finite(pol)) then begin
  ; try to fix some NANs by replacing by a finite value that can be flagged later
   b = finite(pol)
   bad = where(b eq 0)
   pol(bad) = 1000.
   if n_elements(pol) gt 10000 then begin
      filtered = median(pol,7)
      if n_elements(bad)/float(n_elements(pol)) lt 0.1 then pol(bad) = filtered(bad)
   endif
endif

if not min(finite(theta)) then begin
 ; try to fix some NANs by replacing by a finite value that can be flagged later
   b = finite(theta)
   bad = where(b eq 0)
   theta(bad) = 1000.
   if n_elements(theta) gt 10000 then begin
      filtered = median(theta,7)
      if n_elements(bad)/float(n_elements(theta)) lt 0.1 then theta(bad) = filtered(bad)
   endif
endif

end


pro mpi_iterate_pol,I0,I60,I120,TL0,TR0,TL60,TR60,TL120,TR120,I,P,THETA,status
;
; Iteratively solves for I, P, Theta from intensities in polarizers P0, P60, P120

; This code starts from the output of another code that gives a good approximation
;  to I (arbitrary units), P (between 0 and 1), Theta (degrees). It iteratively 
;  improves the estimate and returns the improved I, P, Theta.
;  
;  Note that single elements, not arrays, must be input
;  
;  Input values are I0, I60 and I120, the intensities recorded with the polarizers
;  P0, P60 and P120.  The transmission coefficients are TL0 (T parallel for polarizer 0),
;  TR0 (T perpendicular for polarizer 0) and likewise for polarizers 60 and 120.
;  
;  If any of I0, I60, or I120 I or P are negative, not finite, or not
;  single element arrays, the program returns with no change and
;  status is set to 3.
;
;  If the calculation was successful the status is 0 on return.
;
;  Verion 1.0 by R. West, 7 March, 2014.


off0 = -0.5 ; from lab calibration
off60 = 61.8
off120 = 120.8

status = 3

; no change to input if the signal is negative or something wrong with inputs:
; requires a pre-estimation of I, P, Theta
if n_elements(I0) + n_elements(I60) + n_elements(I120) + n_elements(I) +$
   n_elements(P) + n_elements(Theta) ne 6 then goto, exit
if min([i,p,i0,i60,i120]) le 0. then goto, exit 
if not finite(i+p+theta+I0+I60+I120) then goto, exit

; Calculate I0, I60, I120 from I, p, theta

Ip = I*p & Iu = I - Ip

loopcount = 0

loop:
loopcount = loopcount + 1

I0_test = Iu*(TL0 + TR0)/2 + Ip*(TR0 + (TL0-TR0)*cos((theta-off0)/!radeg)^2)
I60_test = Iu*(TL60 + TR60)/2 + Ip*(TL60*cos((theta-off60)/!radeg)^2 + $
                                    TR60*sin((theta-off60)/!radeg)^2)
I120_test = Iu*(TL120 + TR120)/2 + Ip*(TL120*cos((theta-off120)/!radeg)^2 + $
                                       TR120*sin((theta-off120)/!radeg)^2)

Diff = [I0 - I0_test,I60-I60_test,I120-I120_test]
  
  ; derivatives with respect to Iu, Ip and theta
  
d_I0d_iu = (TL0 + TR0)/2
d_I0d_ip = (TL0*cos((theta-off0)/!radeg)^2 + TR0*sin((theta-off0)/!radeg)^2)
d_i0d_theta = Ip*(TR0-TL0)*sin(2*(theta-off0)/!radeg)/!radeg

d_I60d_iu = (TL60 + TR60)/2
d_I60d_ip = (TL60*cos((theta-off60)/!radeg)^2 + TR60*sin((theta-off60)/!radeg)^2)
d_i60d_theta = Ip*(TR60-TL60)*sin(2*(theta-off60)/!radeg)/!radeg
  
d_I120d_iu = (TL120 + TR120)/2
d_I120d_ip = (TL120*cos((theta-off120)/!radeg)^2 + TR120*sin((theta-off120)/!radeg)^2)
d_i120d_theta = Ip*(TR120-TL120)*sin(2*(theta-off120)/!radeg)/!radeg
  
dm = [[d_I0d_iu,d_I0d_ip,d_i0d_theta],[d_I60d_iu,d_I60d_ip,d_i60d_theta],$
      [ d_I120d_iu,d_I120d_ip,d_i120d_theta]]

idm = invert(dm,status,/double)
if status ne 0 then goto, exit  ; exit if singular or a small povot
  
deltas = diff#idm

; check results 

Iu = Iu + float(deltas[0])
Ip = Ip + float(deltas[1])

I = Iu + Ip
P = Ip/I

theta = theta + float(deltas[2])

if loopcount lt 3 then goto, loop 

;  stop

exit:

end


pro mpi_image_offset,image1,image2,xoff,yoff,silent=silent

;  This program cross-correlates two images to find the offsets in x
;  and y.
;
;  Input:  Image1, Image2: base image and offset image arrays
;
;  Output:  xoff, yoff: the shift in x and y between the two images
;
;  Note: uses convol_fft, which requires IDL 8.1 or later; if using
;  earlier version of IDL, user can swap this out with the convolve.pro
;  function in the IDL astronomy library

  num_params = n_params()

  if num_params lt 4 then begin
     print,' Error in image_offset: too few parameters. Calling sequence:' 
     print,'     image_offset, image1, image2, xoff, yoff'
     xoff = 0 & yoff = 0
     return
  endif

;  Find the steepest gradients in the images (morph_gradient).  Use
;  convolv_fft to produce the cross-correlation.  The location of the
;  maximum of the resulting image gives the offsets.  To get the
;  fractional part of the offsets fit the peak of the convolution with
;  a 2-D Gaussian and solve for the location of the peak to a fraction
;  of a pixel.  Where there are sharp features that correlate well
;  this method is good to about 0.1 pixel or perhaps a little better.
;
  s = size(image1)
  s2 = size(image2)

  if s2(1) ne s(1) or s2(2) ne s(2)  then begin
     print,' Error in image_offset: image dimensions must be identical.'
     print,'     size(image1) = ',s
     print,'     size(image2) = ',s2
     xoff = 0 & yoff = 0
     return
  endif
  
  r = 2
  disc = shift(dist(2*r+1),r,r) le r
  
  temp1 = (image1 - min(image1))*250./(max(image1)-min(image1))
  test1 = morph_gradient(temp1,disc)

  temp2 = (image2 - min(image2))*250./(max(image2)-min(image2))
  test2 = morph_gradient(temp2,disc)

; make the edges 0.0 so that edge effects do not influence the result

  test1(*,0) = 0.
  test1(*,1) = 0.
  test1(0,*) = 0.
  test1(1,*) = 0.
  test1(*,s(2)-1) = 0.
  test1(*,s(2)-2) = 0.
  test1(s(1)-1,*) = 0.
  test1(s(1)-2,*) = 0.

  test2(*,0) = 0.
  test2(*,1) = 0.
  test2(0,*) = 0.
  test2(1,*) = 0.
  test2(*,s(2)-1) = 0.
  test2(*,s(2)-2) = 0.
  test2(s(1)-1,*) = 0.
  test2(s(1)-2,*) = 0.

  corrimage = convol_fft(test1,test2,/correlate)
  corrmax = max(corrimage,m)

  csamp = m mod s(1)
  cline = m/s(2)

; Next solve for the sub-pixel location of the maximum of the correlation
; image assuming the correlation image can be approximated by a parabolic
; shape in line and sample direction: y = y2 + b*(x-x2) + c*(x-x2)^2.

  y1 = corrimage(csamp-1,cline)
  y2 = corrimage(csamp,cline)
  y3 = corrimage(csamp+1,cline)

  b = 0.5*(y3-y1)
  c = y1 + b - y2
  xdelta = -b/(2.*c)
  eps_samp = ((0.03/80.)*(y2/c)^2) < 0.5

  y1 = corrimage(csamp,cline-1)
  y3 = corrimage(csamp,cline+1)
  
  b = 0.5*(y3-y1)
  c = y1 + b - y2
  ydelta = -b/(2.*c)
  eps_line = ((0.03/80.)*(y2/c)^2) < 0.5

  if abs(xdelta) gt 0.6 then begin
     xdelta = 0.0
     if not keyword_set(silent) then print,' Warning: Poor correlation in x image offset.'
  endif

  xoff = (m mod (s(1))) - s(1)/2 + xdelta
  
  if abs(ydelta) gt 0.6 then begin
     ydelta = 0.01
     if not keyword_set(silent) then print,' Warning: Poor correlation in y image offset.'
  endif

  yoff = (m/s(2) - s(2)/2) + ydelta

; final tweak: brute force computation of residuals
; look for minimum RMS residuals for small residual shifts

  residuals = fltarr(3,3)
  
  temp = median(image2,7)
  temp(0:1,*) = 0.0
  temp(*,0:1) = 0.0
  temp(s(1)-2:s(1)-1,*) = 0.0
  temp(*,s(2)-2:s(2)-1) = 0.0
  threshold = 0.1*max(temp)
  
  z = where(temp gt threshold)
  
  xo = fltarr(3,3) & yo = xo
  
  for j = 0,2 do begin
     
     for k = 0,2 do begin

        yo(j,k) = yoff + eps_line*(j-1)
        xo(j,k) = xoff + eps_samp*(k-1)
        image3 = mpi_image_shift(image1, xo(j,k),yo(j,k))
        diff = image3-image2
        diffsq = median(diff*diff,7) ; filters out cosmic rays
        diffsq(z) = 0.0              ; exclude sky background and edge noise
        residuals(j,k) = total(diffsq)
        
     endfor
  endfor
  
  x = min(residuals,n)
  
  j = n/3
  k = n mod 3
  
  xoff = xo(j,k)
  yoff = yo(j,k)

  if not finite(xoff + yoff) then begin
     if not keyword_set(silent) then print,' Image alignment failed!'
     xoff = 0
     yoff = 0
  endif

  return
  
end

function mpi_image_shift,in_image,x_shift,y_shift

; Shifts an image given supplied x and y offsets
;
; Calling sequence:
;    output_image = mpi_image_shift(in_image, x_shift, y_shift)

  s = size(in_image)
  numsamps = s(1)
  numlines = s(2)
  samps = float(make_array(size=s)) & lines = samps
  samps(0:numsamps-1,0) = findgen(numsamps)
  for i = 1,numlines-1 do samps(*,i) = samps(*,0)
  lines(0,*) = findgen(numlines)
  for i = 1,numsamps-1 do lines(i,*) = lines(0,*)  
  
  x = (samps + x_shift) < (numsamps-1) > 0
  y = (lines + y_shift) < (numlines-1) > 0
  
  out_image = interpolate(in_image,x,y)
  
  x = samps + x_shift
  y = lines + y_shift
  
  z = where( x lt 0. or y lt 0. or x ge numsamps or y ge numlines)
  
  if total(z) gt 0. then out_image(z) = 0.0

  return,out_image
end




;==============================================================================================


function make_polar_image,file1,file2,file3,align=align,flip=flip,outfile=outfile,silent=silent,debug=debug,tvals=tvals

; See description, usage, and version history at top of file.

if n_params() lt 2 then begin

print,'make_polar_image.pro'
print,'--------------------'
print,''
print,'This function ingests registered or unregistered, calibrated,'
print,'polarized images from the Cassini ISS cameras. Input images must be'
print,'in VICAR format, and specified in sets of two or three, with filters'
print,'consisting of either:'
print,'   1) P0, P60 and P120 (NAC)'
print,'   2) IRP0 and IRP90 (WAC)'
print,'   3) CLR and IRP0 (NAC and WAC)'
print,'with matching colors (except for CLR) in the opposite filter'
print,'position. The order of input images is irrelevant, only that they'
print,'constitute a matching set.'
print,''
print,'Invoking the program:'
print,''
print,'  result = make_polar_image(file1,file2,[file3],[/align],[/flip],$'
print,'          [outfile=outfile],[silent=silent])'
print,''
print,'  Set the /align keyword to co-register the images if they have'
print,'   not already been co-registered.'
print,'  Set the /flip keyword to flip the output arrays about the x'
print,'   (sample) axis'
print,'  Set the /silent keyword to suppress warning and info messages (but'
print,'   not error messages).'
print,'  Set the outfile keyword equal to the filename of a VICAR-format'
print,'   file containing the calculated intensity. This file will be given'
print,'   the same label as file1 to track calibration history.'
print,''
print,'See make_polar_image_readme.txt for more information.'
return,-1

endif
  
; initialize cisscal variables:
@cisscal_common.pro
CisscalVers = '3.7'
IBatch = -1
debugflag = 1
Cisscal_Log,/nolog

  CLR_FLAG = 0 ; SET IF ONE IF THE COMBINATION IS CLR, IRP0
p = n_params()

if p lt 2 then begin
   print,'Error in call to make_polar_image:'
   print,'     Must specify two files for IR, three for VIS polarizers.'
   print,'     You specified ',p
   return,-1
endif

if file_test(file1) eq 0 then begin
   print,'Error in call to make_polar_image:'
   print,'     File ',file1,' does not exist'
   return,-1
endif

if file_test(file2) eq 0 then begin
   print,'Error in call to make_polar_image:'
   print,'     File ',file2,' does not exist'
   return,-1
endif

ImgObj1 = OBJ_NEW('CassImg')
ImgObj1->ReadVic, file1
data1 = ImgObj1->Image()
label1 = ImgObj1->LabelText()

OutObj = ImgObj1

ImgObj2 = OBJ_NEW('CassImg')
ImgObj2->ReadVic, file2
data2 = ImgObj2->Image()
label2 = ImgObj2->LabelText()

vpos = strpos(label1,'CISSCAL')
cisscal_version = float(strmid(label1,vpos+8,3))

t = ''''

cal_factor = 1.0

;
; The calibration of the polarizers has changed significantly up to version 3.7.
;  Users should only use version 3.7 or higher

if cisscal_version lt 3.7 then begin
   if not keyword_set(silent) then print,$
      'Intensity will be inaccurate. Use Cisscal 3.7 or higher for polarization studies'
endif

;--------------------------------------------------------------
; For IR polarizers: NAC IRP0+CLR; WAC IRP0+IRP90; WAC IRP0+CLR
;--------------------------------------------------------------

if p eq 2 then begin   

   tt = strpos(label1,'INSTRUMENT_ID') + 15
   camera = strmid(label1,tt,5)

  ; process IR filters

   larray = [label1,label2]
   
   p0index = strpos(larray,t+'IRP0'+t)
   z = where(p0index gt 0)
   if total(z) lt 0 then begin
    print,'Error in make_polar_image: Neither of the input images is IRP0'
    print,'     (Note: Intensity + IRP90 functionality not yet implemented.)'
    return,-1
   endif

   if camera eq 'ISSNA' then begin
;      if not keyword_set(silent) then $
;         print, 'WARNING: NAC IRP0 is not yet calibrated.  Using WAC Transmission values!!!'
      filter = strmid(larray(z),p0index(z)+8,3)
   endif else begin
      filter = strmid(larray(z),p0index(z)-5,3)
   endelse 

   if total(z) lt 0 then begin
      if camera eq 'ISSNA' then $
         print, 'Error in make_polar_image: Only 2 of 3 files specified' else $
            print, 'Error in make_polar_image: No image labels contain IRP0'
      return,-1
   endif
   if n_elements(z) gt 1 then begin
      print, 'Error in make_polar_image: More than one file contains IRP0'
      return,-1
   endif

   case z of
      0: begin
         irp0 = data1
         label = label2
      end
      1: begin 
         irp0 = data2
         label = label1
      end
   endcase

   if strpos(label,t+filter+t) lt 0 then begin
      print,'Error in make_polar_image: Filters dont match:'
      print,'     IRP0 is coupled with filter ',filter
      if z eq 0 then print,'     '+file2+' is not' else print,'     '+file1+' is not'
      return,-1
   endif

  ; transmissions for IRP0:
   f = 1.0
   delta = 1.0

   case filter of
      
      'MT2': begin
         
         case camera of
            'ISSWA': begin
               measured_t10_plus_t20 = 0.950293
               measured_t190_plus_t290 = 0.922205
               t290 = 0.0
               t190 = measured_t190_plus_t290
               t20 = measured_t10_plus_t20 - measured_t190_plus_t290
               t10 = measured_t10_plus_t20 - t20
               
               tl0 =  0.932 & tr0 = 0.0184
               tl90 =  0.922 & tr90 = 0.0000
               
            end
            
            'ISSNA': begin               
               measured_t10_plus_t20 = 0.97247767
               measured_t190_plus_t290 = 0.922205
               t290 = 0.0
               t190 = measured_t190_plus_t290
               t20 = 0.03
               t10 = measured_t10_plus_t20 - t20
               
               CoefsP0 =  [     0.682611,    -0.395150]

;               tr0 =  0.00005 & tl0 = (2*coefsp0[0] + coefsp0[1]) - tr0
               tl0 =      0.970 & tr0 =   0.0005 ; from fitting 
;               tl0 =      0.870 & tr0 =   0.1005 ; adjusted to match other results
               
            end
         endcase
      end
      
      'CB2': begin
        
         case camera of
            'ISSWA': begin

               delta = -0.01
               measured_t10_plus_t20 = 0.974210
               measured_t190_plus_t290 = 0.936367
               t290 = 0.0
               t190 = measured_t190_plus_t290
               t20 = measured_t10_plus_t20 - measured_t190_plus_t290 + delta
               t10 = measured_t10_plus_t20 - t20
         
               tl0 =  0.952 & tr0 = 0.0217
               tl90 =  0.936 & tr90 = 0.0000
            end
         
            'ISSNA': begin
               CoefsP0 =  [     0.649469,    -0.325677]
               Tr90_lab = 5.0e-05
               t1_plus_t2 = 2*coefsp0[0] + coefsp0[1]
               tr0 = Tr90_lab
               tl0 = t1_plus_t2 - tr0
               tl0 = 0.973211  & tr0 = 5.00000e-05 ; from fitting
;         tl0 = 0.873211  & tr0 = 0.10 + 5.00000e-05 ; adjusted to match other filters
            end
         endcase
      end
      
      'MT3': begin
        
         case camera of
            'ISSWA': begin
               
               delta = -0.020
               measured_t10_plus_t20 = 1.02065
               measured_t190_plus_t290 = 0.964200
               t290 = 0.0
               t190 = measured_t190_plus_t290
               t20 = measured_t10_plus_t20 - measured_t190_plus_t290 + delta
               t10 = measured_t10_plus_t20 - t20    
               
               tl0 =  0.991088 & tr0 = 0.0293053
               tl90 =   0.963519 & tr90 = 0.00005
               
            end
            
            'ISSNA': Begin
               
               CoefsP0 =  [     0.754710,    -0.499213]
               Tr90_lab = 5.0e-05
               t1_plus_t2 = 2*coefsp0[0] + coefsp0[1]
               tr0 = Tr90_lab
               tl0 = t1_plus_t2 - tr0
               
               tl0 =  1.0  & tr0 = 0.015 ; Compromise between matching t1+t2 and t1-t2
               
            end
            
         endcase
         
      end
      
      'IR1': begin
        
         case camera of
            'ISSWA': begin      
        
               delta = 0.00
               measured_t10_plus_t20 = 0.97565258
               measured_t190_plus_t290 = 0.982639
               t290 = 0.0
               t190 = measured_t190_plus_t290
;         t10 = 0.993 & t20 = measured_t10_plus_t20 - t10
               t20 =  0.02
               t10 = measured_t10_plus_t20 - t20
            end   
            
            'ISSNA': Begin

               CoefsP0 =  [     0.659661,    -0.346494]
               Tr90_lab = 5.0e-05
               t1_plus_t2 = 2*coefsp0[0] + coefsp0[1]
               tr0 = Tr90_lab
               tl0 = t1_plus_t2 - tr0

               tl0 =  0.973  & tr0 = 0.00005

            end  
         endcase
        
      end

      
      'IR3': begin
         
         case camera of
            'ISSWA': begin
               delta = 0.00
               measured_t10_plus_t20 = 1.00865
               measured_t190_plus_t290 = 0.982639
               t290 = 0.0
               t190 = measured_t190_plus_t290
;               t10 = 0.993 & t20 = measured_t10_plus_t20 - t10
               t20 = measured_t10_plus_t20 - measured_t190_plus_t290 + delta
               t10 = measured_t10_plus_t20 - t20
               CoefsP0 =  [     0.705382,    -0.402231]
               CoefsP90 = [     0.694937,    -0.407414]

               tl0 =  0.989198 & tr0 = 0.0193352
               tl90 =    0.982410 & tr90 = 0.00005
               
            end

            'ISSNA': Begin

                  CoefsP0 =  [     0.717990,    -0.417544]
                  Tr90_lab = 5.0e-05
                  t1_plus_t2 = 2*coefsp0[0] + coefsp0[1]
                  tr0 = Tr90_lab
                  tl0 = t1_plus_t2 - tr0
                  
                  tl0 =  1.0  & tr0 = 0.01839

               end
         endcase
            
      end
   
      'IR4': begin
         delta = 0.00
         measured_t10_plus_t20 = 0.990549
         measured_t190_plus_t290 = 0.989540
         t290 = 0.0
         t190 = measured_t190_plus_t290
;        t10 = 0.993 & t20 = measured_t10_plus_t20 - t10
         t20 = measured_t10_plus_t20 - measured_t190_plus_t290 + delta
         t10 = measured_t10_plus_t20 - t20
         CoefsP0 =  [     0.708331,    -0.426658]
         CoefsP90 = [     0.706776,    -0.424951]

         tl0 =  0.99 & tr0 = 0.0
         tl90 =    0.988552 & tr90 = 0.00005

      end

      'CB3': begin
         
         case camera of
            'ISSWA': Begin      ; WAC
               delta = -0.005
               measured_t10_plus_t20 = 0.995187
               measured_t190_plus_t290 = 0.978361
               t290 = 0.0
               t190 = measured_t190_plus_t290
               t20 = measured_t10_plus_t20 - measured_t190_plus_t290 + delta
               t10 = measured_t10_plus_t20 - t20

               tl0 =  0.980503 & tr0 = 0.0144489
               tl90 =  0.976388 & tr90 = 0.00005

            end
            'ISSNA': begin      ; NAC
               CoefsP0 =  [     0.681167,    -0.346179]
               Tr90_lab = 5.0e-05
               t1_plus_t2 = 2*coefsp0[0] + coefsp0[1]
               tr0 = Tr90_lab
               tl0 = t1_plus_t2 - tr0
               
               tl0 =  1.0 & tr0 = 0.01616

            end
         endcase

      end
      
      'IR2': begin
         delta = -0.000
         measured_t10_plus_t20 = 1.03207
         measured_t190_plus_t290 = 0.975589
         t290 = 0.02
         t190 = measured_t190_plus_t290 - t290
;         t20 = measured_t10_plus_t20 - measured_t190_plus_t290 + delta
         t20 = 0.033
         t10 = measured_t10_plus_t20 - t20     
         CoefsP0 =  [     0.752568,    -0.473102]
         CoefsP90 = [     0.718798,    -0.467205]

         tl0 =  1.0 & tr0 = 0.0320381
         tl90 =    0.970341 & tr90 = 0.00005

      end
      
      else: begin
         print,'Error: Filter '+filter+' not supported by make_polar_image.pro'
         return,-1
      end
      
   endcase

   if keyword_set(debug) then begin   ; Debugging...
      print,'Enter /DEBUG mode...'
      print,''
      print,'Filter ',filter
   
      print, 't10 t20 ',t10, t20
      if camera eq 'ISSWA' then print, 't190 t290 ',t190, t290
      print,'t10+t20 ',t10+t20
      if camera eq 'ISSWA' then print,'t190+t290 ',t190+t290
      r1 = (t10-t20) / (t10+t20)
      print, 't10-t20 / t10+t20 ',r1
      if camera eq 'ISSWA' then r2 = (t190-t290) / (t190+t290)
      if camera eq 'ISSWA' then print,'t190-t290 / t190+t290 ',r2
      if camera eq 'ISSWA' then r3 = r1/r2
      if camera eq 'ISSWA' then print,'ratio ',r3
      print,'f, delta',f,delta
      tab = string(9b)
      
      if max([t10,t20,t190,t290]) gt 1.0 then begin
         print,'[t10,t20,t190,t290] = ',[t10,t20,t190,t290],$
               ' Maxiumum greater than 1 in make_polar_image'
         stop
      endif
      if min([t10,t20,t190,t290]) lt 0.0 then begin
         print,'[t10,t20,t190,t290] = ',[t10,t20,t190,t290],$
               ' Minimum greater than 0 in make_polar_image'
         stop
      endif
      
      stop
   endif
      
   if strpos(label,t+'IRP90'+t) gt 0 then begin         ;IRP0 and IRP90
      case z of                                         ;--------------
         0: irp90 = data2
         1: irp90 = data1
      endcase
      p90index = strpos(label,t+'IRP90'+t)
      filter2 = strmid(larray(z),p0index(z)-5,3)
         
        ; align images if necesary:   
      if keyword_set(align) then begin
         s = size(irp0)
         numlines = s(2)
         
         if not keyword_set(silent) then print,'Aligning IR images...'
         
         mpi_image_offset,irp90,irp0,xoff,yoff;,silent=silent
         irp90 = mpi_image_shift(irp90,xoff,yoff)

         if not keyword_set(silent) then begin
            print,' IRP90 x offset = ',xoff
            print,' IRP90 y offset = ',yoff
         endif
         
         marginx = abs(xoff)
         marginy = abs(yoff)      
      endif
         
;     6/2019 update by B. West:     
      x = 0.0 ; replace with cos^2(sunax) if you want Ip.  Otherwise you get q.
      numerator = 2*(-IRP0*T190 + IRP90*T20 + IRP90*T10*x + IRP0*T190*x - IRP90*T20*x - $
                     IRP0*T290*x)
      denom = (T10*T190 - T20*T290)*(-1 + 2*x)
      iu = numerator/denom
      
      numerator = -IRP90*T10 + IRP0*T190 - IRP90*T20 + IRP0*T290
      denom = (T10*T190 - T20*T290)*(-1 + 2*x)
      ip = numerator/denom
      q_90_0 = -numerator/(T10*T190 - T20*T290)
         
      intensity = (IRP90*(T10 - T20) + IRP0*(T190 - T290))/(T10*T190 - T20*T290)

   endif else begin                                     ;IRP0 and CLR
    
    CLR_FLAG = 1
    
      case z of                                         ;------------
         0: intensity = data2
         1: intensity = data1
      endcase
      
; align images if necesary:   
      if keyword_set(align) then begin
         s = size(irp0)
         numlines = s(2)
            
         if not keyword_set(silent) then print,'Aligning IR images...'
            
         mpi_image_offset,irp0,intensity,xoff,yoff,silent=silent
         irp0 = mpi_image_shift(irp0,xoff,yoff)
  
         if not keyword_set(silent) then begin
            print,' CLR x offset = ',xoff
            print,' CLR y offset = ',yoff
         endif
            
         marginx = abs(xoff)
         marginy = abs(yoff)      
      endif

;      ip0 = intensity + 2.*(irp0 - intensity*t10)/(t10 - t20) ; old formula
;      
;      for tesing purpposes only:
;       xarray = [0.999997, 0.99999, 0.751827, 0.751405, 0.425854, 0.425370, 4.09890e-06, 2.30557e-06]
;       irp0 = intensity*(0.11/0.4)

;     6/2019 update by R. West:      
;      IRP90 = (IRP0*(T290-T190) + intensity*(T10*T190 - T20*T290))/(T10-T20)
;      x = 0.0 ; replace with cos^2(sunaz) if you want Ip.  Otherwise you get q.
;      numerator = -IRP90*T10 + IRP0*T190 - IRP90*T20 + IRP0*T290
;      denom = (T10*T190 - T20*T290)*(-1 + 2*x)
;      ip = numerator/denom
      q_90_0 = (Intensity*(Tl0 + Tr0) - 2*IRP0)/(Tl0-Tr0)

;     for testing purposes only:
;      ip = -(((intensity > 1.e-03)*(t10 + t20)-2*(irp0 > 1.e-03)))/((1.-2.*x)*(t10 - t20))
;      x2 = 1-x
;      ip2 = -(((intensity > 1.e-03)*(t10 + t20)-2*(irp0 > 1.e-03)))/((1.-2.*x2)*(t10 - t20))
;      if min(ip) lt 0.0 then stop
         
   endelse

; stokes parameter Q:

   q = make_array(size=size(data1),value=-2.0)
;   z0 = where(intensity gt 0.01)
   z0 = where(intensity gt 0.002)
;   q[z0] = (ip[z0])*(t10*(1-2.*x) + t20*(2.*x-1))/(t10-t20)
   q[z0] = q_90_0[z0]
   q_over_i = make_array(size=size(q))
   q_over_i[z0] = q[z0]/intensity[z0] > (-1.0) < 1.0

   if keyword_set(debug) then begin
;   plot,intensity,q_over_i,psym=1
      z1 = where(intensity gt 0.01)
      tot = mean(q_over_i[z1])
      iu = intensity-ip
      iutot = mean(iu[z1])
      iptot = mean(ip[z1])
      avgq = tot
      BTOT = IUTOT*(t10+t20)/2 + iptot*(t10*x + T20*(1-x))
      atot = mean(intensity[z1])
      ip_over_a_tot = (2.*btot/atot-(t10+t20))/((t10-t20)*(2.*x-1))
      p_from_q = avgq*(t10-t20)/(t10*(1-2.*x) + t20*(2.*x-1))
      print, btot/atot, Iptot/atot , iutot/atot, iptot/atot, ip_over_a_tot, tot, avgq
      stop
   endif
   
; Return  I, Q/I from IR polarizers

   q = q_over_i
   s = size(q)
   outstruct = {intensity:fltarr(s[2],s[2]),q:fltarr(s[2],s[2])}
      
   if(keyword_set(flip)) then begin
      outstruct.intensity = rotate(intensity,7)
      outstruct.q = rotate(q,7)
   endif else begin
      outstruct.intensity = intensity
      outstruct.q = q
   endelse

   if keyword_set(tvals) then begin
    case CLR_FLAG of
       0: tvals = [tl0,tr0,tl90,tr90]
       1: tvals = [tl0,tr0]
    endcase
   endif
      
endif else begin
      
;------------------------------------------
; For NAC Visible polarizers: P0, P60, P120
;------------------------------------------

   result = file_test(file3)
   if result eq 0 then begin
      print,'Error in call to make_polar_image:'
      print,'     File ',file3,' does not exist'
      return,-1
   endif
      
   ImgObj3 = OBJ_NEW('CassImg')
   ImgObj3->ReadVic, file3
   data3 = ImgObj3->Image()
   label3 = ImgObj3->LabelText()  
   
   larray = [label1,label2,label3]
   
   p0index = strpos(larray,t+'P0'+t)
   z = where(p0index gt 0)
   if total(z) lt 0 then begin
      print, 'Error in make_polar_image: No image labels contain P0'
      return,-1
   endif
   if n_elements(z) gt 1 then begin
      print, 'Error in make_polar_image: More than one file contains P0'
      return,-1
   endif
   
   case z of
      0: ip0 = data1
      1: ip0 = data2
      2: ip0 = data3
   endcase
   
   filter = strmid(larray(z),p0index(z)+6,3)
   
   p60index = strpos(larray,t+'P60'+t)
   z = where(p60index gt 0)
   if total(z) lt 0 then begin
      print, 'Error in make_polar_image: No image labels contain P60'
      return,-1
   endif
   if n_elements(z) gt 1 then begin
      print, 'Error in make_polar_image: More than one file contains P60'
      return,-1
   endif
   
   case z of
      0: ip60 = data1
      1: ip60 = data2
      2: ip60 = data3
   endcase
   
   filter2 = strmid(larray(z),p60index(z)+7,3)
   
   p120index = strpos(larray,t+'P120'+t)
   z = where(p120index gt 0)
   if total(z) lt 0 then begin
      print, 'Error in make_polar_image: No image labels contain P120'
      return,-1
   endif
   if n_elements(z) gt 1 then begin
      print, 'Error in make_polar_image: More than one file contains P120'
      return,-1
   endif
   
   case z of
      0: ip120 = data1
      1: ip120 = data2
      2: ip120 = data3
   endcase
   filter3 = strmid(larray(z),p120index(z)+8,3)
   
   if filter ne filter2 or filter ne filter3 then begin
      print,'Error in make_polar_image. Non-polarized filters don''t match:'
      print, filter1
      print, filter2
      print, filter3
      return,-1
   endif
   
; transmissions for P0, P60, P120
   case filter of
      
      'GRN': begin
         T1 = 0.648 & T2 = 0.037 & delta_t = 0.026
         
         coefsp0     =   [0.521247,    -0.308693]
         coefsp60    =   [0.493532,    -0.300177]
         coefsp120   =   [0.485647,    -0.295102]
         
         tl0 =  0.716797 & tr0 = 0.0170043
         tl60 =  0.683687 & tr60 = 0.0032
         tl120 =  0.6725874 & tr120 = 0.00360489

      end
      
      'UV3': begin
         T1 = 0.54  & T2 = 0.087 & delta_t = 0.043
                  
         coefsp0  =     [0.527108,    -0.345680]
         coefsp60  =     [0.484203,    -0.336778]
         coefsp120  =    [0.478450,    -0.336094]

         t0sum = 2*coefsp0[0] + coefsp0[1]
         t60sum = 2*coefsp60[0] + coefsp60[1]
         t120sum = 2*coefsp120[0] + coefsp120[1]
         
         p0diff = -coefsp0[1]
         p60diff = -coefsp60[1]
         p120diff = -coefsp120[1]

         ; Force the perpendicular transmission to be the same as measured in the lab\
         ; for P0
         Tr60_lab = 0.02

         tl0 =  0.658 & tr0 = 0.0506
         tl60 =  0.612 & tr60 = 0.0200
         tl120 =  0.606 & tr120 = 0.0151

         i0 = t0sum/(tl0 + tr0)
         ip = p0diff/(tl0 - tr0)
         ratio0 = ip/i0
         print,'polarization for filter 0 = ',ratio0
         i0 = t60sum/(tl60 + tr60)
         ip = p60diff/(tl60 - tr60)
         ratio60 = ip/i0
         print,'polarization for filter 60 = ',ratio60
         i0 = t120sum/(tl120 + tr120)
         ip = p120diff/(tl120 - tr120)
         ratio120 = ip/i0
         print,'polarization for filter 120 = ',ratio120

      end
      
      'BL2': begin
         T1 = 0.602 & T2 = 0.046 & delta_t = 0.03
                  
         coefsp0 =  [     0.531389,     -0.356971]
         coefsp60 =  [     0.501767,     -0.357583]
         coefsp120 = [     0.490849,     -0.343358]
         
         tl0 =  0.670346 & tr0 = 0.0354594
         tl60 =  0.640948 & tr60 = 0.00500
         tl120 =  0.640948 & tr120 = 0.00500
         
      end
      
      'MT2': begin
         T1 = 0.793 & T2 = 0.085 & delta_t = 0.051
         
         coefsp0 =  [     0.641899,     -0.302541]
         coefsp60 =  [     0.600992,     -0.322660]
         coefsp120 = [     0.597324,     -0.314228]

         tl0 =  0.846617 & tr0 = 0.134640
         tl60 =  0.819324 & tr60 = 0.0600
         tl120 =  0.809950 & tr120 =  0.0704696

      end
      
      'CB2': begin
         T1 = 0.793 & T2 = 0.085 & delta_t = 0.051
                
         coefsp0 =  [     0.640008,     -0.236507]
         coefsp60 =  [     0.597792,     -0.253027]
         coefsp120 = [     0.597006,     -0.256408]
         
         t0sum = 2*coefsp0[0] + coefsp0[1]
         t60sum = 2*coefsp60[0] + coefsp60[1]
         t120sum = 2*coefsp120[0] + coefsp120[1]

         tl0 =  0.868792 & tr0 = 0.174717
         tl60 =  0.842557 & tr60 = 0.1000
         tl120 =  0.845042 & tr120 = 0.0925624
      end
      
      'MT1': begin
         T1 = 0.655 & T2 = 0.018 & delta_t = 0.03
         
         coefsp0 =  [     0.516046,     -0.299105]
         coefsp60 =  [     0.482446,     -0.288021]
         coefsp120 = [     0.476074,     -0.283985]
         

         tl0 =  0.714838 & tr0 = 0.0181493
         tl60 =  0.673871 & tr60 = 0.0030
         tl120 =  0.664817 & tr120 = 0.00334644    
      end
      
      'CB1': begin
         T1 = 0.654  & T2 = 0.022 & delta_t = 0.032
         
         coefsp0 =  [     0.511250,     -0.284567]
         coefsp60 =  [     0.475892,     -0.274390]
         coefsp120 = [     0.470803,     -0.270663]
         
         tl0 =  0.717114 & tr0 = 0.0208187
         tl60 =  0.674394 & tr60 = 0.0030
         tl120 =  0.666609 & tr120 = 0.00433427
         
      end
      
      else: begin
         print,'Error: Filter '+filter+' not yet supported by make_polar_image.pro'
         return,-1
      end
      
   endcase

   if keyword_set(align) then begin
      s = size(ip0)
      numlines = s(2)
      
      if not keyword_set(silent) then print,'Aligning images...'
      
      mpi_image_offset,ip60,ip0,xoff60,yoff60,silent=silent
      ip60 = mpi_image_shift(ip60,xoff60,yoff60)
      
      if not keyword_set(silent) then begin
         print,' P60 x offset = ',xoff60
         print,' P60 y offset = ',yoff60
      endif      

      mpi_image_offset,ip120,ip0,xoff120,yoff120,silent=silent
      ip120 = mpi_image_shift(ip120,xoff120,yoff120)
      
      if not keyword_set(silent) then begin
         print,' P120 x offset = ',xoff120
         print,' P120 y offset = ',yoff120
      endif

      marginx = max([abs(xoff60),abs(xoff120)])
      marginy = max([abs(yoff60),abs(yoff120)])
   endif

; Calculate Intensity, Polarization, Theta:

   s = size(ip60)
   radians = !pi/180.           ; radians per degree

   mpi_calc_ipt,Ip0,Ip60,Ip120,T1,T2,delta_t,Intensity,Polarization,Theta
   if min(finite(intensity)) eq 0 or min(finite(polarization)) eq 0 or $ 
      min(finite(theta)) eq 0 then begin
      if not keyword_set(silent) then print,' Warning: Non-finite values in output arrays!'
   endif 

   a = finite(theta)
   theta_bad = where(a ne 1)
   if total(theta_bad) gt 0 then theta[theta_bad] = 0.0
   
; set border region to 0 where there is not sufficient overlap
   if keyword_set(align) then begin
      intensity[0:marginx,*] = 0.
      intensity[s[1]-marginx-1:s[1]-1,*] = 0.
      intensity[*,0:marginy] = 0.
      intensity[*,s[2]-marginy-1:s[2]-1] = 0.
      polarization[0:marginx,*] = 0.
      polarization[s[1]-marginx-1:s[1]-1,*] = 0.
      polarization[*,0:marginy] = 0.
      polarization[*,s[2]-marginy-1:s[2]-1] = 0.
      theta[0:marginx,*] = 0.
      theta[s[1]-marginx-1:s[1]-1,*] = 0.
      theta[*,0:marginy] = 0.
      theta[*,s[2]-marginy-1:s[2]-1] = 0.
   endif
   
   diffi0 = make_array(size=size(ip0)) & diffi60 = diffi0 & diffi120 = diffi0
   iu = intensity*(1.0-polarization)
   ip = intensity-iu
   
   diffi0 = ip0-(iu*(TL0+TR0)/2 + Ip*(TL0*cos((theta+0.5)/!radeg)^2 + $
                                      TR0*sin((theta+0.5)/!radeg)^2))
   diffi60 = ip60-(iu*(TL60+TR60)/2 + Ip*(TL60*cos((theta-61.8)/!radeg)^2 + $
                                          TR60*sin((theta-60.8)/!radeg)^2))
   diffi120 = ip120-(iu*(TL120+TR120)/2 + Ip*(TL120*cos((theta-120.8)/!radeg)^2 + $
                                              TR120*sin((theta-120.8)/!radeg)^2))
   rms_image = (sqrt((diffi0^2 + diffi60^2 + diffi120^2)/3.))
   
   rms = total(rms_image)

   ; improve the result with iteration

   tempi = intensity
   temppol = polarization
   temptheta = theta
   status_image = make_array(S[1],S[2],/byte,value=3)
   
   for k = 0,s[2]-1 do begin
      for j = 0,s[1]-1 do begin
 ;     for k = 256, 256 do begin ; for debugging
 ;     for j = 400,400 do begin
         ti = intensity[j,k]
         tp = polarization[j,k]
         ttheta = theta[j,k]
         status = byte(3)
         mpi_iterate_pol,IP0[j,k],IP60[j,k],IP120[j,k],TL0,TR0,TL60,TR60,TL120,TR120,$
                         ti,tp,ttheta,status
         tempI[j,k] = ti
         tempPol[j,k] = tp
         tempTHETA[j,k] = ttheta
         status_image[j,k] = status
      endfor
   endfor
   
   z = where(status_image eq 0)
   bad = where(status_image ne 0)
   if not keyword_set(silent) then $
      print,'Fraction of image with bad pixels is ',n_elements(bad)/(float(n_elements(intensity)))
   intensity[z] = tempi[z]
   polarization[z] = temppol[z]
   theta[z] = temptheta[z]
   
   diffi0 = make_array(size=size(ip0)) & diffi60 = diffi0 & diffi120 = diffi0
   iu = intensity*(1.0-polarization)
   ip = intensity-iu
   diffi0 = ip0-(iu*(TL0+TR0)/2 + Ip*(TL0*cos((theta+0.5)/!radeg)^2 + $
                                      TR0*sin((theta+0.5)/!radeg)^2))
   diffi60 = ip60-(iu*(TL60+TR60)/2 + Ip*(TL60*cos((theta-61.8)/!radeg)^2 + $
                                          TR60*sin((theta-60.8)/!radeg)^2))
   diffi120 = ip120-(iu*(TL120+TR120)/2 + Ip*(TL120*cos((theta-120.8)/!radeg)^2 + $
                                              TR120*sin((theta-120.8)/!radeg)^2))
   rms_image = (sqrt((diffi0^2 + diffi60^2 + diffi120^2)/3.))

   rms = total(rms_image)
   
; return Intensity, Polarization, Theta as a structure
   
   outstruct = {intensity:fltarr(s[2],s[2]),polarization:fltarr(s[2],s[2]),theta:fltarr(s[2],s[2])}
      
   if(keyword_set(flip)) then begin
      outstruct.intensity = rotate(intensity,7)
      outstruct.polarization = rotate(polarization,7)
      outstruct.theta = rotate(theta,7)
   endif else begin
      outstruct.intensity = intensity
      outstruct.polarization = polarization
      outstruct.theta = theta
   endelse
   
endelse

  
; write to Vicar-formatted file include label from file1. 
if keyword_set(outfile) then begin
   if not keyword_set(silent) then print, 'Writing intensity array in VICAR format to file: ',outfile
   OutObj->writevic,outfile,pol=outstruct.intensity
endif

IF OBJ_VALID(OutObj) THEN OBJ_DESTROY,OutObj
IF OBJ_VALID(ImgObj1) THEN OBJ_DESTROY,ImgObj1
IF OBJ_VALID(ImgObj2) THEN OBJ_DESTROY,ImgObj2
IF OBJ_VALID(ImgObj3) THEN OBJ_DESTROY,ImgObj3

if keyword_set(tvals) then begin

if CLR_FLAG then p = 1
  case p of
    1: tvals = [tl0,tr0]
    2: tvals = [tl0,tr0,tl90,tr90]
    3: tvals = [tl0,tr0,tl60,tr60,tl120,tr120]
  endcase
endif


return,outstruct

end
