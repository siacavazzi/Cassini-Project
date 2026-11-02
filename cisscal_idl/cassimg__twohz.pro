;;  cassimg__twohz.pro
;;
;;	Subtracts "2 Hz noise" using image data or overclocked pixels
;;      - algorithm by Daren Scot Wilson,  December 23, 2003
;;      - integrated into CISSCAL by Ben Knowles, January 4, 2004
;
; INPUT:
;
;	mask
;		ignored if /use_overclocked is given 
;		if a 2D array, indicates where image has background pixels.
;	         0 = bkg pixel
;		 1 = object, glitch or cosmic ray pixel
;		if a scalar value, is used as a threshold to make a mask
;
;	overclocked pixel mode: 
;	        Forces use of overclocked pixels instead of image data
;	        May result in noisier image, less completely removed 2Hz noise
;   	        Necessary for images with little black space visible
;
; OUTPUT:
;		self's image array is updated with a cleaner image
;
; ALGORITHM:
;
; First the 2Hz signal is reconstructed from the image data or the overclocked pixels
; This is found by averaging or finding the median value for each scan line
; of a smoothed image.   The smoothing is essential to reducing quantization noise
; for an accurate low-noise estimate of the original 2Hz interference signal.
; While the signal value is found for each scan line, pixels that are non-background
; should be ignored.   
;
; This signal is then filtered to remove the DC and low frequency components
; (unless /keep_dc is given)   Details of filter described below.
;
; Finally we make a 2D image out of the 1D signal and subtract it from the original.
;
; In the case where the image mean algorithm is requested, but no
; theshold is specified (for instance, in batch mode), the
; AutoStarLevel code, below, is used to determine an appropriate theshold.
;

;-----------------------
; Missing pixel routines:

PRO HealMissingMin, img, altmissing
        img = img*(1-altmissing) + altmissing * ( shift(img,0,1) < shift(img,0,-1) )
    END

PRO HealMissingAvg, img, altmissing
    img = img*(1-altmissing) + altmissing * fix(0.5*(shift(img,0,1) + 1.0*shift(img,0,-1)))
END

PRO ZeroMissing, img, altmissing
        ; fill altmissing pixels with zeros
        img = img * (1-altmissing)
END

PRO FindMissing, img, missing, missingchunks, altmissing
;
; INPUT
;       img:  2D array of raw image
;
; OUTPUT
;       missing:  2D array of all missing pixels
;       missingchunks: big missing areas, like top or bottom of image
;       altmissing:  alternating lines, typ. from lossless compression
;
;       for all these, 0=pixel okay,  1=pixel is missing
;       missing[] may indicate some pixels missing that are neither in
;       a missing chunk or alternating lines (but no known examples yet)
;
  newmissing = (size(missing))[0]
  w = (size(img))[1]

  if newmissing eq 0 then begin
      missing=img eq 0          ; find all zeros
       ; For 8LSB images, missing[] is polluted with accidental zeros
       ; use 1D median on each row to filter
       ; solid runs of missing pixels
      for y=0,w-1 do missing[*,y] = median(missing[*,y], 9)
  endif

  hsum = total(missing,1) ge w-5 ; allow for some side crud errors
  hsum = median(hsum, 3)         ; filter out alternating lines, single lines
  missingchunks = (replicate(1,w)#hsum) and missing
  altmissing = missing and (not shift(missing,0,1)) and (not shift(missing,0,-1))

END


function AutoStarLevel, img,                       $
		sigmas=sigmas,                             $
		bkgmean=bkgmean, bkgsigma=bkgsigma
    
; Return a threshold level good for separating stars from messy background 
; noise.  Also helps do useful things with this: report number of candidate 
; stars, produce a just-background image.
;
; INPUT
;   img = 2D array image of starfield
;   
; OPTIONAL INPUT
;   sigmas = how many sigma above the bkg pixel distribution mean
;   to put the threshold?   Default is probably 6.0 (check below)
;
; OPTIONAL OUTPUT
;
;   bkgmean:  mean value of bkg
;   bkgsigma:  std dev of bkg    
;
;
; RETURN
;   scalar value to use in e.g.  (img > retvalue) to define stars
;
; Written by Daren Scot Wilson, CICLOPS

; remove unused dimensions
 imgd=reform(img)
    
 if n_elements(sigmas) eq 0 then sigmas=6.0
 sigmas_used = sigmas

; First attempt to find the average level of bkg noise, and its sigma,
; not minding the stars and crud;  m and s are likely to be off due
; to huge pull from large DNs in stars
; Also save these image stats as StarStackVars 
 imgmin=min(imgd)
 imgmax=max(imgd)
 imgmean=mean(imgd)
 imgstd=stddev(imgd)
 
 m=imgmean    
 s=imgstd
 
    ; find the average level and sigma again, this time clipping down
    ; any peaks (stars, cosmic ray spots,  blemishes etc.)
    ; We also cut off low-value outliers just in case any exist
 highcut = m+8*s
 lowcut  = m-8*s
 imgd = (imgd < highcut) > lowcut
 m = mean(imgd )
 s = stddev(imgd )
 
    ; Second cut, should now be better centered on distr. of just bkg pixels
 highcut = m+sigmas*s
 lowcut  = m-sigmas*s
 imgd = (imgd < highcut) > lowcut
 m = mean(imgd )
 s = stddev(imgd )
 
 bkgmean=m
 bkgsigma=s    
 
 thresh = m+sigmas*s
 return, thresh
END


PRO CassImg::TwoHz

@cisscal_common.pro	; include COMMON definitions

; Don't attempt to subtract 2 hz noise if LUT, gain state lower
; than 3 (12 e-/DN). Note: user already alerted by debias code.
If self.ConvType EQ 'TABLE' and self.GainState LT 3 THEN RETURN
  
in_image=*self.ImageP

; define missing pixels array:
if PTR_VALID(self.MissingP) then missing = *self.MissingP else $
  missing = -1

; get summation mode:
sum = self.Labels -> Get('INSTRUMENT_MODE_ID')

IF DebugFlag gt 0 THEN BEGIN
   CISSCAL_Log,'Subtracting 2 Hz noise:'
ENDIF

IF sum NE 'FULL' then begin
    IF DebugFlag gt 0 then begin
          CISSCAL_Log,'  2 Hz removal not optimized for summed images; skipped'
    ENDIF
    RETURN
 ENDIF

; overclock method:

IF NOT (*(*(*CalOptions).twohz).imagemean).onoff THEN BEGIN

   IF DebugFlag gt 0 THEN CISSCAL_Log,'  Using overclocked pixel values to estimate 2 Hz noise.'

    IF NOT PTR_VALID(self.OverClkP) THEN BEGIN
        IF DebugFlag gt 0 THEN BEGIN
            CISSCAL_Log, '  No valid prefix bytes to supply overclocked values; 2 Hz removal skipped'
        ENDIF
        RETURN
    ENDIF
    
    overclock = self->OverclockAvg()
    
    IF self.ConvType EQ 'TABLE' THEN overclock = cisscal_delut(overclock)
    
    IF(overclock[0] GT 2*overclock[1]) THEN overclock[0] = overclock[1]
    overclock = float(overclock)
    n_pixels = n_elements(overclock)
    overclock = reform(overclock, n_pixels, /overwrite)

   ; fill in any missing data:
    missingoc = where(overclock eq 0.0,nmiss)

    if nmiss gt 0 and nmiss lt n_pixels then begin   
       goodoc = where(overclock ne 0.0,ngoodoc)
       goodoverclock = overclock[goodoc]
       junk = linfit(goodoc,goodoverclock,yfit=gofit)
       gofit = temporary(interpol(gofit,goodoc,indgen(n_pixels)))
       overclock[missingoc] = gofit[missingoc]
    endif

                                ; fit a line to overclocked pixels
                                ; (which has already been removed by
                                ; debias routine):
    junk = linfit(indgen(n_pixels),overclock,yfit=linbias)    
    hum = overclock - linbias

    newflag='Subtracted 2Hz noise (overclocked pixels)'

ENDIF ELSE BEGIN                ; image mean method
    
    IF DebugFlag gt 0 THEN CISSCAL_Log, '  Using image pixel values to estimate 2 Hz noise.'
    
       ; fill in missing lines and missing chunks of image
       ; for better mask and to prevent ringing at hard edges 
       ; when filtering 2hz signal

    FindMissing, in_image, missing, missingchunks, altmissing
    *self.MissingP = missing

    HealMissingAvg, in_image, altmissing
    fillvalue = total(in_image*(1-missing)) / (total(1-missing)  >0)
                                ; average of image, non-missing pixels only
    in_image = (1-missingchunks)*in_image +  missingchunks*fillvalue
    
; use selected mask file, otherwise create mask with autostarlevel
; (mask array is assumed to have 1s for masked pixels, 0s for non-masked)
        
    maskfile = (*(*(*CalOptions).twohz).imagemean).maskfile
    
    IF maskfile eq '' THEN BEGIN
        
        thresh = (*(*(*CalOptions).twohz).imagemean).threshold
        pixrange = (*(*(*CalOptions).twohz).imagemean).pixrange
        
        if thresh lt 0 then begin
            IF DebugFlag gt 0 THEN BEGIN
                CISSCAL_Log, '  Threshold value must be greater than 0. Cannot create mask; 2 Hz removal skipped'
            ENDIF
            RETURN
        endif
        
        if thresh eq 0 then begin
            IF DebugFlag gt 0 THEN CISSCAL_Log,$
              '  Automatically determining image threshold level...'
            thresh = AutoStarLevel(in_image,sigmas=4) ;using missing-pixel-corrected array
        endif
        
        if pixrange le 0 then pixrange = 9 ;default
        
        IF DebugFlag gt 0 THEN BEGIN
            CISSCAL_Log, '  Constructing a mask from given threshold =' + $
                         strtrim(string(thresh),2)
            CISSCAL_Log, '  and pixel extension range =' + strtrim(string(pixrange),2)
        ENDIF
                                ; This trickery creates a mask larger
                                ; than (image gt thresh) by about (rspot) pixels
        mask = float(in_image gt thresh) 
        mask = float(smooth(mask,pixrange,/edge_truncate) gt (0.5/(pixrange^2)))
        mask = float(smooth(mask,pixrange,/edge_truncate) gt 0.25)
        
    ENDIF ELSE BEGIN     
        IF DebugFlag gt 0 THEN CISSCAL_Log, '  Using user-specified mask file.'
        
        MaskObj = OBJ_NEW('CassImg') 
        
        MaskObj->ReadVic, maskfile, /Quiet, /NotCass
        mask = float(MaskObj->Image())
        
        OBJ_DESTROY, MaskObj    ; Finished with object: reclaim the space
       
    ENDELSE

   ; stick mask array in self.maskP:
    IF (PTR_VALID(self.MaskP)) THEN PTR_FREE,self.MaskP
    self.MaskP = PTR_NEW(mask)
    
    ones = replicate(1.,self.NL)
    ngoodpix_in_row = total(1.0-mask, 1)
    avgbkg = total(in_image*(1.0-mask), 1) / (ngoodpix_in_row > 1.0)
    tmpimg = (mask)*(ones#avgbkg) + (1.0-mask)*in_image	
    tmpimg[*,0] = tmpimg[*,2]                     ; replace first two
    tmpimg[*,1] = tmpimg[*,2]
    tmpimg[*,self.NL-1] = tmpimg[*,self.NL-2]     ; and last lines with neighbors

   ; ignore first 12 and last 5 pixels of each line - may be abnormal
   ; in some operational modes.
        
    hum = fltarr(self.NL)
    for i = 0l,self.NL-1 do hum[i] = median(tmpimg[12:self.NS-5,i])
    
    newflag='Subtracted 2Hz noise (image mean)'

ENDELSE
    

;----------------------------
; Filter out low freq part
;----------------------------

; Filter kernel was based loosely on a butterworth design,
; The 2Hz noise has typically 20-50 cycles per frame (vertical)
; so passband is flat and 100% from about k=15 up,  zero response at k=0,
; very low response for few-cycle per image height, smooth transition to 
; prevent ringing, phase shift characteristics seem to be unimiportant
; in the transition zone.  But we do want zero phase shift in passband
; for accurate 2Hz noise modelling. 6th order seems to do very well at 
; separating dark current from 2Hz hum. Call the result "AC Hum" as if
; we were EEs designing audio stuff.
;
; Additional trickery - because filtering acts as if we chose cyclic
; boundary conditions, we would get huge ringing effects along the 
; top and bottom of the image, due to it having an overall gradient.
; e.g. if dark current wasn't subtracted. To prevent this, we
; temporarily double the size of the hum signal and stich the original 
; signal with a mirrored copy of itself. This entails "secretly" 
; implementing a filter width twice the size asked for.

;------------------------------------------
; New method from Daren's filterhum44h.pro:
;          (updated by BDK for CISSCAL 3.7)
;------------------------------------------

w=(size(hum))[1]

 ; if overclocked pixels, replace top and bottom lines with neighbors:
IF not (*(*(*CalOptions).twohz).imagemean).onoff THEN BEGIN
   hum[0] = hum[2]
   hum[1] = hum[2]
   hum[w-1] = hum[w-2]
ENDIF

humx = fltarr(w+200)    
humx[100:100+w-1] = hum
for i=0,99 do humx[99-i] = mean(hum[0:i])
for i=0,99 do humx[100+w+i] = mean(hum[w-1-i:w-1])

 ; remove slow-varying component:

if self.Instrument eq 'ISSNA' THEN sw = 15 else sw = 10
sg = SavGol(sw,sw,0,4)          ; create filter

lbreak = self->LineBreak()
if lbreak-2 ge 49 and lbreak le w-51 then begin ; discontinuity

   ; if line break exists, split into two parts and filter each
   ; separately

   humx1 = [humx[0:99+lbreak-1],fltarr(100)]
   for i=0,99 do humx1[99+lbreak+i] = mean(humx1[99+lbreak-1-i:99+lbreak-1])
   humx2 = [fltarr(100),humx[100+lbreak+1:n_elements(humx)-1]]
   for i=0,99 do humx2[99-i] = mean(humx2[100:100+i])
   shumx1 = convol(humx1,sg,/edge_truncate)   ; use standard filter for lower freq hum
   sg2 = SavGol(3,3,0,4)   ; use narrower filter for higher frequency hum
   shumx2 = convol(humx2,sg2,/edge_truncate)
   slowpart1 = smooth(smooth(smooth(humx1,31),49),49)
   slowpart2 = smooth(smooth(smooth(humx2,31),49),49)
   slowpart = [slowpart1[0:n_elements(slowpart1)-101],$
               0.0,0.0,$            ; ignore pixels on either side of discontinuity
               slowpart2[100:n_elements(slowpart2)-1]]
   shumx = [shumx1[0:n_elements(shumx1)-101],$
            0.0,0.0,$
            shumx2[100:n_elements(shumx2)-1]]
   shumx = shumx-slowpart
   shumx[100+lbreak-1:100+lbreak] = 0  ; ignore pixels on either side of discontinuity

endif else begin        ; no discontinuity or chunks too small: don't split up
   shumx   = convol(humx, sg, /edge_truncate)
   slowpart = smooth(smooth(smooth(smooth(humx,21),31),49),49)
   shumx = shumx-slowpart

endelse

hum = shumx[100:100+w-1]

;----------------------------------------
; Subtract the hum signal from the image:
;----------------------------------------

ones = replicate(1.,self.NL)
tmp = *self.ImageP - ones # hum
tmp = (1-missing)*tmp    ; restore zero to all missing pixels

*self.ImageP = temporary(tmp)

;	Update calibration history in image label:
;                 (revamped for CISSCAL 3.7, 5/13)

; append 2 hz removal info to bias_subtraction_text keyword 
; (which will already be populated):
oldflag = self.Labels->Get('BIAS_SUBTRACTION_TEXT')
; if BIAS_SUBTRACTION_TEXT already exists, append:
if (size(oldflag))[1] eq 7 then newflag = oldflag + '; ' + newflag
junk=self.Labels->Set('BIAS_SUBTRACTION_TEXT',newflag,1)

END
