;;	cassimg__correctionfactors.pro
;;	Correct image for ad-hoc factors
;;
;;	Doug	October 2000
;;      
;;      Revisions:
;;         - added calibration history - BDK, 4/02
;;         - polarization correction - BDK, 8/07
;;         - revamped output label history - BDK 5/13
;;         - polarization correction modified - BDK, 4/14
;;         - fixed CassLabels class attributes bug - M. Showalter, 7/17

PRO CassImg::CorrectionFactors

@cisscal_common.pro	; include COMMON definitions

  IF self.ShutStateID EQ 'DISABLED' THEN BEGIN
     IF DebugFlag GT 0 THEN $
        CISSCAL_Log,'Shutter disabled. Skipping absolute flux correction...'
     RETURN
  ENDIF 
  
  Filter1 = self.Filter1
  Filter2 = self.Filter2

  IF DebugFlag gt 0 THEN BEGIN
     CISSCAL_Log,'Applying absolute flux correction:'
  ENDIF

  ; First apply standard correction factors. Note that 
  ; Filt + pol combos take Filt + clr correction:

  if strpos(Filter1+Filter2,'P') ge 0 then begin
     if self.Instrument eq 'ISSNA' then Filter1 = 'CL1'
     if self.Instrument eq 'ISSWA' then Filter2 = 'CL2'
  endif

  CFFile = 'correctionfactors_qecorr.tab'
  CorrFact = ''
  GET_LUN, DBFile
  OPENR, DBFile, CalibrationBaseDir + 'correction/'+ CFFile, ERROR=err
  IF ( err NE 0 ) THEN BEGIN
    IF DebugFlag gt 0 THEN CISSCAL_Log, '  Correction factor database not found: unable to search for factor'
    CorrFact = '1'
  ENDIF ELSE BEGIN
    while not eof(DBFile) do begin
        text=''
        readf, DBFile, text
        if strpos(text, '\begindata') ge 0 then break
    endwhile

    WHILE ( (CorrFact EQ '') AND (NOT EOF(DBFile))) DO BEGIN
;	Keep looking...
      LineBuf=''
      READF, DBFile, LineBuf
      LineBuf = STRCOMPRESS(LineBuf)	; collapse whitespace to single spaces
      Fields = STRSPLIT(LineBuf,' ',/extract) ; tokenize
      IF Fields[0] NE '' THEN BEGIN
        IF ((Fields[0] EQ self.Instrument) $
          AND ( Fields[1] EQ Filter1 ) $
          AND ( Fields[2] EQ Filter2 ) ) THEN CorrFact = strtrim(Fields[3],2)
      ENDIF
    ENDWHILE
    IF (CorrFact EQ '') THEN BEGIN
      IF DebugFlag gt 0 THEN CISSCAL_Log, '  Correction factor not found in database'
      CorrFact = '1'
    ENDIF
  ENDELSE
  FREE_LUN, DBFile

  If DebugFlag gt 0 THEN CISSCAL_Log, '  Divided by correction factor for '+Filter1+','+Filter2+' = ' + CorrFact

  *self.ImageP = *self.ImageP / float(CorrFact)

;	Update calibration history in image label:
;		(added by Ben Knowles, 4/02)
;               (revamped for CISSCAL 3.7, 5/13)

newhistory='Divided by absolute correction factor of '+CorrFact

if self.Labels->Have('RADIOMETRIC_CORRECTION_TEXT') then begin

   oldhistory = self.Labels->Get('RADIOMETRIC_CORRECTION_TEXT',index=rindex)

; if keyword found and is the SECOND to last one set, we know it was set by
; current CISSCAL process, so append new history:

  ; Modified by MRS, 7/2017:
  ; In GDL and in the formal IDL definition, you can only access the attributes of
  ; a class from a function that operates on that class. This function operates on
  ; class CassImg, so the attribute .NLabels of class CassLabels is inaccessible.
  ; Use of the new function CassLabels::Get_NLabels() solves this problem.

;if rindex eq (self.Labels).NLabels-2 then begin                ; old
   if rindex eq self.Labels->Get_NLabels()-2 then begin ; new
      junk=self.Labels->Set('RADIOMETRIC_CORRECTION_TEXT',oldhistory + '; ' + newhistory,1)
   endif else begin
      junk=self.Labels->Set('RADIOMETRIC_CORRECTION_TEXT',newhistory,1,/new)
   endelse
endif else begin
   junk=self.Labels->Set('RADIOMETRIC_CORRECTION_TEXT',newhistory,1,/new)
endelse

IF DebugFlag eq 2 THEN CISSCAL_Log, '  Pixel flux extrema ', self->DNRange()

END
