;;	cassimg_debias.pro
;;	Subtract bias using embedded OFFSET or overclocked pixels
;;	Kevin	14th August 1998

PRO CassImg::DeBias

;	The image bias level may be embedded in the
;	headers. Otherwise, we can use the overclocked pixels attached
;	to the image, which are in attribute *OverClkP
;	(these have been extracted from the prefixed bytes of each line
;	in the image VICAR file).

;	Preferred option anyway now is to model bias from oveclocked pixel value vector,
;	smoothing the values available with the "digital filter"
;	built-in IDL function and appropriate parameters.
;	The effect of this is to remove the horizontal "banding" seen in flight images.
;	This algorithm was imported in October 2001 from
;	 Vance Haemmerle's "debias2" procedure of March 2000

;	Overclocked pixel values should be at *self.OverClkP, and already corrected
;	 to reverse 12-to-8 bit encoding if this was used for this image.

;       Update (January 2004 - Ben Knowles):
;       2-Hz noise removal ("horizontal banding" mentioned above) is
;       now performed by a separate, much-improved algorithm. The bias
;       subtraction is accomplished by using either the
;       BIAS_STRIP_MEAN in the image label, or a linear fit to the
;       overclocked pixels; the user can choose between these methods.

@cisscal_common.pro	; include COMMON definitions

IF DebugFlag THEN BEGIN
   CISSCAL_Log, 'Subtracting bias:'
ENDIF
  
if (*(*CalOptions).bias).biasstripmean then begin
    biasstrip = 1
    tryoc = 0

    if self.enctype eq 'LOSSY' and float(self.Fsw) le 1.3 then begin
        If DebugFlag gt 0 then CISSCAL_Log, '  Lossy encoding: cannot use BIAS_STRIP_MEAN.'
        tryoc = 1
    endif

    if tryoc eq 1 then begin
        if not PTR_VALID(self.OverClkP) then begin
            If DebugFlag gt 0 then CISSCAL_Log, '  No overclocked pixels found: cannot remove bias.'
            return
        endif else begin
            If DebugFlag gt 0 then CISSCAL_Log, '  Using overclocked pixels instead...'
            biasstrip = 0
        endelse
    endif
endif else begin
    if not PTR_VALID(self.OverClkP) then begin
        If DebugFlag gt 0 then CISSCAL_Log, '  No overclocked pixels found.'

        if self.enctype eq 'LOSSY' and float(self.Fsw) le 1.3 then begin
            If DebugFlag gt 0 then CISSCAL_Log, $
              '  Lossy encoding: cannot use BIAS_STRIP_MEAN; cannot remove bias.'
            return
        endif
            
        If DebugFlag gt 0 then CISSCAL_Log, '    Using BIAS_STRIP_MEAN instead...'
        biasstrip = 1
    endif else begin
       if self.convtype eq 'TABLE' and self.gainstate lt 3 then begin
          If DebugFlag gt 0 then begin
             CISSCAL_Log,'  Table-encoded image with gain state < 3;'
             CISSCAL_Log,'    Using BIAS_STRIP_MEAN to remove bias and skipping 2 Hz removal...'
          ENDIF
          biasstrip = 1
       endif else begin
          biasstrip = 0
       endelse
    endelse
endelse

if biasstrip then begin  ; use BIAS_STRIP_MEAN in image label
    if self.Offset[0] lt 0.0 then begin
       If DebugFlag gt 0 then CISSCAL_Log, $
          '  BIAS_STRIP_MEAN value corrupt; cannot remove bias.'
       return
    endif

   if self.convtype eq 'TABLE' then $
      bias = cisscal_delut(fix(self.Offset[0])) else bias = self.Offset[0]

    Image=*self.ImageP
    outimage = float(Image) - bias
    subs = WHERE(Image EQ 0, count)
    IF(count NE 0) THEN outimage[subs] = 0.0

    newflag='Subtracted bias (BIAS_STRIP_MEAN)'
endif else begin         ; use overclocked pixels

    ; create bias template from overclocks:

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

    ; fit a line to overclocked pixels:
    junk = linfit(indgen(n_pixels),overclock,yfit=bias)

    Image=*self.ImageP
    outimage = float(Image)
    FOR i=0,n_pixels-1 DO outimage[*,i] = outimage[*,i] - bias[i]
    subs = WHERE(Image EQ 0, count)
    IF(count NE 0) THEN outimage[subs] = 0.

    newflag='Subtracted bias (overclocked pixels)'
endelse 


*self.ImageP = outimage

If DebugFlag gt 0 then CISSCAL_Log,'  ',newflag

;	Update calibration history in image label:
;		(added by Ben Knowles, 4/02)
;               (revamped for CISSCAL 3.7, 5/13)

junk=self.Labels->Set('BIAS_SUBTRACTION_TEXT',newflag,1,/new)

IF DebugFlag eq 2 THEN CISSCAL_Log, '  DN extrema ', self->DNRange()

END
