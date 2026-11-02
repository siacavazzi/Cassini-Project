;;	cassimg__dividebyflats.pro
;;	Correct image for sensitivity variations across the field
;;	by dividing by flat field image
;;
;;      The flat field is generated on the fly from the slope file
;;       by inverting and normalizing.
;;	There is a text database file in the slope files directory
;;	 that maps filter combinations (and camera temperature)
;;	 to the corresponding slope field files.
;;
;;	Kevin	January 1999

PRO CassImg::DivideByFlats

@cisscal_common.pro	; include COMMON definitions

IF self.ShutStateID EQ 'DISABLED' THEN BEGIN
   IF DebugFlag GT 0 THEN $
      CISSCAL_Log,'Shutter disabled. Skipping flat field correction...'
   RETURN
ENDIF
  
IF DebugFlag gt 0 THEN BEGIN
   CISSCAL_Log,'Dividing by flat field:'
ENDIF

; Get slope directory paths from environment variables, if possible,
; otherwise assume CalibrationBaseDir is root:

SlopeBaseDir = CalibrationBaseDir + 'slope/'
IF STRMID(SlopeBaseDir, STRLEN(SlopeBaseDir)-1, 1) NE '/' THEN $
	SlopeBaseDir = SlopeBaseDir + '/'

;	Find the best-match slope file
;	Choose a nominal optics temp name as per ISSCAL
  IF (self.OptT)[0] LT -5.0 THEN Tname = 'm10' ELSE $
    IF (self.OptT)[0] LT 25.0 THEN Tname = 'p5' $
    ELSE TName = 'p25'

  SlopeDBName = 'slope_db_2.tab'
  SlopeFname = ''
  GET_LUN, DBFile
  OPENR, DBFile, SlopeBaseDir+SlopeDBName, ERROR=err
  IF ( err NE 0 ) THEN BEGIN
    If DebugFlag gt 0 THEN CISSCAL_Log, $
      '  Flat field database not found: unable to find ' + SlopeBaseDir+SlopeDBName
  ENDIF ELSE BEGIN
    Filter1 = self.Filter1
    Filter2 = self.Filter2

    while not eof(DBFile) do begin
        text=''
        readf, DBFile, text
        if strpos(text, '\begindata') ge 0 then break
    endwhile
    
    WHILE ( (SlopeFName EQ '') AND (NOT EOF(DBFile))) DO BEGIN
;	Keep looking...
      LineBuf=''
      READF, DBFile, LineBuf
      LineBuf = STRCOMPRESS(LineBuf)	; collapse whitespace to single spaces
      Fields = STRSPLIT(LineBuf,' ',/extract) ; tokenize
      IF Fields[0] NE '' THEN BEGIN	; have tokens OK...
;	Require match for instrument, temperature range name, Filter1, filter2
        IF ((Fields[0] EQ ''''+self.Instrument+'''') $
          AND ((Fields[1] EQ Tname) OR (self.Instrument eq 'ISSWA')) $
          AND ( Fields[2] EQ ''''+Filter1+'''' ) $
          AND ( Fields[3] EQ ''''+Filter2+'''' ) ) THEN SlopeFName = Fields[7]
      ENDIF
    ENDWHILE
  ENDELSE
  FREE_LUN, DBFile

  IF SlopeFName EQ '' THEN BEGIN
     IF DebugFlag gt 0 THEN BEGIN
        CISSCAL_Log, '  No appropriate flat file found in database; flat field correction skipped...'
     ENDIF
     RETURN
  ENDIF ELSE BEGIN
    SlopePath1 = SlopeBaseDir + STRLOWCASE(SlopeFName)

;	Try the standard directory for the slopefile, otherwise try the spare
    SlopeRes = FILE_SEARCH(SlopePath1)
    SlopePath = SlopeRes[0]

    IF SlopePath EQ '' THEN BEGIN
      IF DebugFlag gt 0 THEN CISSCAL_Log, '  Unable to find expected flat field (slope) file: ' + $
		SlopePath1
      RETURN
    ENDIF ELSE BEGIN
      SlopeObj = OBJ_NEW('CassImg')
      IF DebugFlag gt 0 THEN BEGIN
          CISSCAL_Log, '  Found flat field (slope) file: ' + SlopeFName
      ENDIF
      SlopeObj->ReadVic, SlopePath, /Quiet, /NotCass

;	Fetch slope image, rebin to actual image size      
;	*Don't* adjust here for changed pixel size in SUM2 and SUM4 modes
;	instead, this is incorporated into the later division by the
;	solid angle of a pixel

      SlopeImg = REBIN(*SlopeObj.ImageP, self.NS, self.NL)

      IF DebugFlag eq 2 THEN BEGIN
        CISSCAL_Log, '  Slope image raw extrema:', SlopeObj->DNRange()
        CISSCAL_Log, '  Slope image extrema now' + STRING( MIN(SlopeImg)) + STRING(MAX(SlopeImg))
      ENDIF

;       Replace NaN values with 1 before dividing (added 6/29/16):
      bImg = finite(SlopeImg)
      bad = where(bImg eq 0,nbad)

;       Normalize flatield to median of center region:      
      minpix = long(self.NS/2. - 200.*(self.NS/1024.))
      maxpix = long(self.NS/2. + 200.*(self.NS/1024.)) - 1L

      Flatfield = temporary(median(SlopeImg[minpix:maxpix,minpix:maxpix])/SlopeImg)

      if nbad gt 0 then Flatfield[bad] = 1.0

      *self.ImageP = *self.ImageP / Flatfield

;	Finished with the slope object
      OBJ_DESTROY, SlopeObj

      IF DebugFlag eq 2 THEN CISSCAL_Log, '  Pixel extrema ', self->DNRange()

    ENDELSE

  ENDELSE

;	Update calibration history in image label:
;		(added by Ben Knowles, 4/02)
;               (revamped for CISSCAL 3.7, 5/13)

junk=self.Labels->Set('FLATFIELD_CORRECTION_FLAG',1,0,/new)
junk=self.Labels->Set('SLOPE_FILE_NAME',SlopeFName,1,/new)

END
