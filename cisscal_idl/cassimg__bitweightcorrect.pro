;;	cassimg__bitweightcorrect.pro
;;	Correct image for uneven bit weights
;;	Kevin	14th August 1998
;;	Updated 30th December 1998
;;	Calibration history information added 5th April 2002

;	This is done using one of several tables developed
;		from the ground calibration exercises
;	The table to be used depends on:
;		Camera		NAC or WAC
;		GainState	1, 2 or 3
;		Optics temp.	-10, +5 or +25

PRO CassImg::BitWeightCorrect

@cisscal_common.pro	; include COMMON definitions

;	Define whereabouts of bitweight correction files
BitWeightDir = CalibrationBaseDir + 'bitweight/'

IF DebugFlag gt 0 THEN BEGIN
;   CISSCAL_Log
   CISSCAL_Log,'Bit-weight correction:'
ENDIF

;	Skip if lossy-encoded or LUT as per Bob West's algorithm
IF self.EncType EQ 'LOSSY' THEN BEGIN
  IF DebugFlag gt 0 THEN CISSCAL_Log, '  Lossy encoding: skip bit-weight correction as insignificant'
  RETURN
ENDIF

IF self.ConvType EQ 'TABLE' THEN BEGIN
  IF DebugFlag gt 0 THEN CISSCAL_Log, '  LUT encoding: skip bit-weight correction as insignificant'
  RETURN
ENDIF


IF self.Instrument EQ 'ISSNA' THEN Camera = 'NA' $
ELSE IF self.Instrument EQ 'ISSWA' THEN Camera = 'WA' $
ELSE BEGIN
  IF DebugFlag gt 0 THEN CISSCAL_Log, '  Unexpected value for Instrument ID:', self.Instrument
  RETURN
ENDELSE

CalTemps = [ -10, +5, +25 ]
TempDiffs = ABS(CalTemps - self.OptT[0] )

ClosestTemp = CalTemps [ WHERE(TempDiffs EQ MIN(TempDiffs)) ]
UseTemp = ClosestTemp[0]	; Just in case two are equidistant

;CISSCAL_Log, 'Temperature diffs are', TempDiffs, ' using ', useTemp

IF DebugFlag gt 0 THEN CISSCAL_Log, $
  '  Apply bit-weight calibration data for: ', $
  STRING(self.Instrument) + ' at temp ' + STRTRIM(STRING(UseTemp),2) $
  + ' gain ' + STRTRIM(STRING(self.GainState),2)

IF DebugFlag eq 2 THEN CISSCAL_Log, '  DN extrema ', self->DNRange()

; For now, follow ISSCAL algorithm for selecting temperature range
IF self.Instrument EQ 'ISSNA' THEN FName = 'nac' ELSE FName = 'wac'
CASE self.GainState OF
 0: FName = Fname + 'g0'
 1: FName = Fname + 'g1'
 2: FName = Fname + 'g2'
 3: FName = Fname + 'g3'
ELSE: IF DebugFlag gt 0 THEN CISSCAL_Log, '  Unexpected value of gain state:',self.GainState
ENDCASE
IF self.OptT[0] LT -5.0 THEN Fname = FName + 'm10' $
ELSE IF self.OptT[0] LT 25.0 THEN Fname = FName + 'p5' $
ELSE FName = FName + 'p25'

FName = BitWeightDir + FName + '_bwt.tab'
IF DebugFlag eq 2 THEN CISSCAL_Log, '  Looking for bit-weight correction file: ' + FName

;GET_LUN, BWTFile
OPENR, BWTFile, FName, ERROR=err, /get_lun
IF ( err NE 0 ) THEN BEGIN
   IF DebugFlag gt 0 THEN CISSCAL_Log, '  No bit-weight calibration file found. Skipping...'
ENDIF ELSE BEGIN
   weights = fltarr(4096)
   data = -1.0
   text=''
   index = 0
  
   while not eof(BWTFile) do begin
      readf, BWTFile, text
      if strpos(text, '\begindata') ge 0 then break
   endwhile
   
   while not eof(BWTFile) do begin
      readf, BWTFile, data
      weights[index] = data
      index++
   endwhile
  
   CLOSE,BWTFile
   FREE_LUN, BWTFile

;	Use current DNs as indices, constraining them to 0..4095
   Indices = ( *self.ImageP > 0 ) < 4095
   *self.ImageP = Weights[Indices]

;	Update calibration history in image label:
;		(added by Ben Knowles, 4/02)
;               (revamped for CISSCAL 3.7, 4/13)

   junk=self.Labels->Set('UNEVEN_BIT_WEIGHT_CORRECTION_FLAG',1,0,/new)
   
   IF DebugFlag eq 2 THEN CISSCAL_Log, '  DN extrema ', self->DNRange()
ENDELSE

END


