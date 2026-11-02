;;	cassimg__dividebyareapixel.pro
;;	Normalise image by dividing by area of optics
;;	and by solid angle subtended by a pixel
;;	Kevin	30th December 1998

PRO CassImg::DivideByAreaPixel

;	SolidAngle is (FOV of Optics) / (Number of Pixels)
;	OpticsArea is (Diameter of Primary Mirror)^2 * Pi/4
;
;       Optics areas below come from radii in "Final Report, Design
;       and Analysis of Filters for the Cassini Narrow and Wide
;       Optics" by David Hasenauer, May 19, 1994.  
  
;	We will adjust here for the effects of SUM modes
;	(which effectively give pixels of 4 or 16 times normal size)

@cisscal_common.pro	; include COMMON definitions

IF self.ShutStateID EQ 'DISABLED' THEN BEGIN
   IF DebugFlag GT 0 THEN $
      CISSCAL_Log,'Shutter disabled. Skipping optics area/solid angle correction...'
   RETURN
ENDIF
  
IF DebugFlag gt 0 THEN BEGIN
   CISSCAL_Log, 'Dividing by (Optics Area) * (Solid Angle per pixel)...'
ENDIF
IF self.Instrument EQ 'ISSNA' THEN BEGIN
   SolidAngle = 3.58885e-11   ;new
   OpticsArea = 284.86        ;new
ENDIF ELSE IF self.Instrument EQ 'ISSWA' THEN BEGIN
   SolidAngle = 3.56994e-9    ;new
   OpticsArea = 29.43         ;new
ENDIF ELSE BEGIN
    IF DebugFlag gt 0 THEN CISSCAL_Log, '  Unexpected value for Instrument ID:', self.Instrument
    RETURN
ENDELSE

; If I/F mode, assume spectrum integrated over source, so do not 
; divide by solid angle - Ben Knowles (2/2/04):
if (*(*(*CalOptions).flux).ioverf).onoff AND $
  (*(*(*CalOptions).flux).ioverf).specfile ne '' then SolidAngle = 1.0

;	Normalise summed images to real pixels
SumFactor = (self.NS/1024.0) * (self.NL/1024.0)

*self.ImageP = *self.ImageP * SumFactor / ( SolidAngle * OpticsArea)

IF DebugFlag eq 2 THEN CISSCAL_Log, '  Image extrema ', self->DNRange()

;	Update calibration history in image label:
;		(added by Ben Knowles, 4/02)
;               (revamped for CISSCAL 3.7, 4/13)

newhistory='Divided by area/solid angle'
junk=self.Labels->Set('RADIOMETRIC_CORRECTION_TEXT',newhistory,1,/new)

END
