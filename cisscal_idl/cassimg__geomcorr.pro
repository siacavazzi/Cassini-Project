;;	cassimg_geomcorr.pro
;;	Applies geometric distortion correction.
;;	Ben Knowles and Bob West, March 19, 2002

PRO CassImg::GeomCorr

@cisscal_common.pro	; include COMMON definitions

; DESCRIPTION: First this code calculates the amount of geometric
;	distortion in the image based on the camera and filter
;	combination. Note that only a few filters are accounted
;	for thus far. 
;
;	After the appropriate coefficients are chosen, a highly-
;	negative buffer region is added as a perimeter around the
;	image, and a preliminary distortion correction is applied 
;	to determine which edge pixels to throw out. Then the buffer
;	region is reset to an approximation of the adjacent edge
;	pixel values by first blurring the image. Finally, the 
;	distortion correction is repeated with this new buffer
;	region, and the result is written to *self.ImageP.

; Skip correction if shutter disabled:
IF self.ShutStateID EQ 'DISABLED' THEN BEGIN
   IF DebugFlag GT 0 THEN $
      CISSCAL_Log,'Shutter disabled. Skipping geometric correction...'
   RETURN
ENDIF
  
;-------------------------------------
; Examine labels to get various inputs
;-------------------------------------

camera = self.Instrument
filter_1 = self.Filter1
filter_2 = self.Filter2
npix = self.NS

;----------------------------
; Apply distortion correction
;----------------------------

in_image=*self.ImageP

buffsize=12.*npix/1024.		;thickness of buffer zone around image
arrsize=fix(npix+2.*buffsize)

camera_type = strupcase(camera)
filt1 = strupcase(filter_1)
filt2 = strupcase(filter_2)

IF DebugFlag gt 0 THEN BEGIN
   CISSCAL_Log,'Performing geometric correction...'
ENDIF

case camera_type of

; For the NAC:

   'ISSNA': begin
       xcen = 560*arrsize/1024.    ; sample of optical center NAC
       ycen = 500*arrsize/1024.    ; line of optical center NAC
       f_default = 2003.181
       k = 0.0
       
       f = f_default            ; Not much sense in doing separate
                                ; filters for NAC - max. offset error
                                ; is 0.22 pixels at corners
       end

   'ISSWA': begin

; For the WAC:

	xcen=548.*arrsize/1024.  ;  sample of optical center WAC
	ycen=508.*arrsize/1024.  ;  line of optical center WAC
        f_default = 200.956

        k=-0.000062              ;  use for all filters

        DistFile = 'wac_focallengths.tab'
        f = ''
        GET_LUN, DBFile
        OPENR, DBFile, CalibrationBaseDir + 'distortion/'+ DistFile, ERROR=err
        IF ( err NE 0 ) THEN BEGIN
            IF DebugFlag gt 0 THEN CISSCAL_Log, '  Focal length database not found; using default.'
            f = f_default
        ENDIF ELSE BEGIN

            while not eof(DBFile) do begin
                text=''
                readf, DBFile, text
                if strpos(text, '\begindata') ge 0 then break
            endwhile
            
            WHILE (f EQ '') AND (NOT EOF(DBFile)) DO BEGIN
;	Keep looking...
                LineBuf=''
                READF, DBFile, LineBuf
                LineBuf = STRCOMPRESS(LineBuf) ; collapse whitespace to single spaces
                Fields = STRSPLIT(LineBuf,' ',/extract) ; tokenize
                IF Fields[0] NE '' THEN BEGIN ; have tokens OK...
                    IF ( Fields[0] EQ filt1 ) $
                      AND ( Fields[1] EQ filt2 ) THEN f = Fields[2]
                ENDIF
            ENDWHILE
            IF ( f EQ '') THEN BEGIN                                 ;; new IF
                IF DebugFlag gt 0 THEN CISSCAL_Log, '  Focal length not found in database; using default.'
                f = f_default
            ENDIF ELSE BEGIN
                f = float(f)
            ENDELSE
        ENDELSE
        FREE_LUN, DBFile

        If DebugFlag eq 2 THEN CISSCAL_Log, '  Focal length is ' + string(f) + ' mm.'  
    end
    
    else: begin
        IF DebugFlag gt 0 THEN CISSCAL_Log,'  Error: Camera type not recognized'
        RETURN
    end
endcase

	; create undistorted coordinate array:

temp = findgen(arrsize)
Xcorrpx = fltarr(arrsize,arrsize) & Ycorrpx = Xcorrpx
for i = 0,arrsize-1 do begin
    Ycorrpx(i,0:arrsize-1) = temp
    Xcorrpx(0:arrsize-1,i) = temp
endfor

	; apply inverse distortion to array:

Xcorrmm=(Xcorrpx-Xcen)*0.012*(1024./npix)    ;optical x in mm
Ycorrmm=(Ycorrpx-Ycen)*0.012*(1024./npix)    ;optical y in mm

Rsq = Xcorrmm^2 + Ycorrmm^2		     ;distance from oc in mm

Xobsmm=(f/f_default)*Xcorrmm/(1.+k*Rsq)	     ;corrected x in mm
Yobsmm=(f/f_default)*Ycorrmm/(1.+k*Rsq)	     ;corrected y in mm

Xobspx=Xobsmm/(0.012*(1024./npix)) + Xcen    ;convert back to pixel #
Yobspx=Yobsmm/(0.012*(1024./npix)) + Ycen    

	; free some memory:

Rsq=0 & Xcorrpx=0 & Ycorrpx=0 & Xcorrmm=0 & Ycorrmm=0 & Xobsmm=0 & Yobsmm=0

	; Find bad outer pixels (currently requires separate 
	; interpolation, unfortunately). Here, buffer is set
	; to highly negative value, and all negative pixels in
	; interpolated image are labeled "bad" and thrown out:

temp_image=replicate(-1.e38,arrsize,arrsize)
temp_image[buffsize:arrsize-buffsize-1,buffsize:arrsize-buffsize-1]=in_image
temp_image = interpolate(temporary(temp_image),Xobspx,Yobspx,cubic=-0.5)
bad=where(temp_image lt 0,nbad)

temp_image=0	     ;free some memory

	; blur buffered image so that cubic spline doesn't blow up at edges:

blur_image=replicate(!values.f_nan,arrsize,arrsize)
blur_image[buffsize:arrsize-buffsize-1,buffsize:arrsize-buffsize-1]=in_image
blur_image=smooth(temporary(blur_image),fix(buffsize)*2+1,/nan,/edge_truncate)

	; replace middle of blurred buffer image with original image:

blur_image[buffsize:arrsize-buffsize-1,buffsize:arrsize-buffsize-1]=in_image

	; apply distortion correction:

distort_image = interpolate(blur_image,Xobspx,Yobspx,cubic=-0.5)

	; set bad pixels to 0:

if (nbad gt 0) then distort_image[bad]=0

	; truncate to original size:

out_image = distort_image[buffsize:arrsize-buffsize-1,buffsize:arrsize-buffsize-1]

*self.ImageP = out_image

;	Update calibration history in image label:
;		(added 4/02 by Ben Knowles)
;               (revamped for CISSCAL 3.7, 4/13)

junk=self.Labels->Set('GEOMETRY_PROJECTION_TYPE','LINEARIZED',1,/new)

END
