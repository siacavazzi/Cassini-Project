;;	cassimg__dividebyexpot.pro
;;	Method to divide a Cassini image by corrected exposure time
;;	Kevin Beurle	30th December 1998

PRO CassImg::DivideByExpoT

;	Divide image by exposure time,
;	correcting for shutter offset effects
;	(sample dependency of actual exposure time)

@cisscal_common.pro	; include COMMON definitions

ConstOffset = 0.0

IF DebugFlag gt 0 THEN BEGIN
   CISSCAL_Log,'Dividing by exposure time to convert to electrons/sec:'
ENDIF

;	Don't even try to do this for zero-exposure images!
IF self.ExpDur EQ 0 THEN BEGIN
    IF DebugFlag gt 0 THEN BEGIN
        CISSCAL_Log, '  Zero exposure image; skipping division by exposure time'
    ENDIF
  self.PerSecond = 0	; Image remains integrated flux rather than flux
  RETURN
ENDIF

;	Define whereabouts of shutter offset files
ShutterOffsetDir = CalibrationBaseDir + 'offset/'

IF self.Instrument EQ 'ISSNA' THEN FName = 'nacfm_so_' $
	ELSE FName = 'wacfm_so_'

IF (self.OptT)[0] LT -5.0 THEN Fname = FName + 'm10.img' $
ELSE IF (self.OptT)[0] LT 25.0 THEN Fname = FName + 'p5.img' $
ELSE FName = FName + 'p25.img'

FPath = ShutterOffsetDir + FName

GET_LUN, SoFile
OPENR, SoFile, FPath, ERROR=err

IF self.ShutStateID EQ 'DISABLED' THEN BEGIN
   IF DebugFlag GT 0 THEN $
      CISSCAL_Log,'  Shutter disabled. Do not apply shutter offset...'
   ExposureT = self.ExpDur
ENDIF ELSE BEGIN

   IF ( err NE 0 ) THEN BEGIN
      IF DebugFlag gt 0 THEN CISSCAL_Log, '  No shutter offset file found; skipping...'
      ExposureT = self.ExpDur
   ENDIF ELSE BEGIN
      CLOSE,SoFile		; In VICAR format: close it and reopen it as such
      IF DebugFlag gt 0 THEN BEGIN
         CISSCAL_Log, '  Shutter offset file found; applying shutter offset data'
      ENDIF
      OffsetObj=OBJ_NEW('CassImg')
      OffsetObj->ReadVic,FPath,/QUIET,/NotCass
      ShutterOffset = REBIN(OffsetObj->Image(), self.NS)

;	 JPL confirms that these values must be subtracted thus:
      ExposureTVec = self.ExpDur - ShutterOffset

;	Replicate exposure time vector for all lines: the
;	shutter offset variation is with sample number
      ExposureT = TRANSPOSE(INTARR(self.NL)+1)##ExposureTVec

      OBJ_DESTROY, OffsetObj	; Finished with object: reclaim the space
  
   ENDELSE
; Constant shutter offset:
;
; Analysis of Vega images (through S03) points to a value of 2.85 ms
; (correct to within about 0.05 ms for the NAC, less certain for the
; WAC. Use this until better data available. (12/1/2005 - BDK)
; UPDATE: Used azimuthal ring scans to pin down WAC to around 1.8 ms.
; (1/18/2006 - BDK) 
; UPDATE #2: S58 SPICA data gives WAC shutter offset of about 2.86 ms. 
; (9/21/2010 - BDK)
; UPDATE #3: Rhea SATCAL obs from rev 163 give NAC offset of 2.75 and
; WAC offset of 2.67 ms, much less noisy results than using stars.
; (1/31/2013 - BDK)
; UPDATE #4: From S100 Vega (WAC) and 77/78 Tau (NAC): NAC offset of
; 2.51, WAC offset of 2.63, but analysis far more noisy than for Rhea
; so keep previous values. (8/4/2017 - BDK)

   IF self.Instrument EQ 'ISSNA' THEN ConstOffset = 2.75 ELSE ConstOffset = 2.67

   ExposureT = temporary(ExposureT) - ConstOffset

   IF DebugFlag eq 2 THEN $
      CISSCAL_Log, '  Nominal exposure (ms):',self.ExpDur,$
                   '; Corrected exposure range (ms):' + STRING(MIN(ExposureT)) + $
                   ' to' + STRING(MAX(ExposureT))
   
ENDELSE
   
*self.ImageP = *self.ImageP*1000/ExposureT   ; 1000 to scale ms to seconds
self.PerSecond = 1	                     ; Pixel value is now flux (electrons per second)

FREE_LUN, SoFile

IF DebugFlag eq 2 THEN CISSCAL_Log, '  Pixel flux extrema =', self->DNRange()

;	Update calibration history in image label:
;		(added by Ben Knowles, 4/02)
;               (revamped for CISSCAL 3.7, 5/13)

junk=self.Labels->Set('EXPOSURE_CORRECTION_FLAG',1,0,/new)

if (size(ExposureT))[0] eq 2 then $
   junk=self.Labels->Set('SHUTTER_OFFSET_FILE_NAME',FName,1,/new)

if ConstOffset gt 0.0 then begin
   ConstStr = string(ConstOffset,format='(F4.2)') + ' ms'
   junk=self.Labels->Set('EXPOSURE_OFFSET',ConstStr,1,/new)
endif

END
