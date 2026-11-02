;;      cassimg__sensvstime.pro
;;      Correct for sensitivity decline vs. time
;;      Ben Knowles, 12/14/2017
;;        Updated by BDK, 6/2018

PRO CassImg::SensVsTime

; Sensitivity vs. time correction derived from stellar photometry:
;  
; NAC, all data (~8% total decline from S03 to S100):
;          slope = -1.89457e-10
;
; WAC, all data (~3% total decline from S17 to S100):
;          slope = -9.28360e-11
  
@cisscal_common.pro     ; include COMMON definitions

  IF self.ShutStateID EQ 'DISABLED' THEN BEGIN
     IF DebugFlag GT 0 THEN $
        CISSCAL_Log,'Shutter disabled. Skipping sensitivity vs. time correction...'
     RETURN
  ENDIF
  
  imgnum = self.ImgNo

  imgnum_s03 = 1.47036e9
  imgnum_s17 = 1.51463e9

  IF DebugFlag gt 0 THEN BEGIN
     CISSCAL_Log, 'Correcting for sensitivity decline vs. time:'
  ENDIF

  if self.Instrument eq 'ISSNA' and imgnum lt imgnum_s03 then begin
     IF DebugFlag gt 0 THEN CISSCAL_Log,'  No NAC correction before S03; skipped'
     return
  endif
  if self.Instrument eq 'ISSWA' and imgnum lt imgnum_s17 then begin
     IF DebugFlag gt 0 THEN CISSCAL_Log,'  No WAC correction before S17; skipped'
     return
  endif
 
  if self.Instrument eq 'ISSNA' then begin
     senscorr = (1. + 1.89457e-10 * (imgnum - imgnum_s03))
  endif else if self.Instrument eq 'ISSWA' then begin
     senscorr = (1. + 9.28360e-11 * (imgnum - imgnum_s17) )
  endif

   *self.ImageP = *self.ImageP * senscorr

  ; note: abs. correction always run before sens. vs. time correction,
  ; so always append keyword as follows:

   oldhistory = self.Labels->Get('RADIOMETRIC_CORRECTION_TEXT',/quiet)
   newhistory='Multiplied by sensitivity vs. time correction of '+strtrim(string(senscorr),2)

   junk=self.Labels->Set('RADIOMETRIC_CORRECTION_TEXT',oldhistory + '; ' + newhistory,1)
   
   IF DebugFlag gt 0 then begin
      CISSCAL_Log,'  ',newhistory
   ENDIF
   
end
