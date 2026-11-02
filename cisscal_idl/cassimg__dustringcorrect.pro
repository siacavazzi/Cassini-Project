;;	cassimg__dustringcorrect.pro
;;	Correct image for dust ring in image
;;
;;	Doug	November 2000
;;
;;      Updated to handle mottle map and time-dependent ring
;;      correction. - BDK, 9/29/2016

PRO CassImg::DustRingCorrect

@cisscal_common.pro	; include COMMON definitions

IF self.ShutStateID EQ 'DISABLED' THEN BEGIN
   IF DebugFlag GT 0 THEN $
      CISSCAL_Log,'Shutter disabled. Skipping dust ring correction...'
   RETURN
ENDIF
  
; Dust ring and mottling correction for NAC only:
IF self.Instrument EQ 'ISSNA' THEN BEGIN

   epochs = [1308947228L,1472331833L,1502443470,1508671907L,1548379322L,$
             1559626712L,1574706112L,1584661741L,1605235887L,1639829174L,$
             1766118561L,1804499182L]
   
   dustindex = max(where(epochs le self.ImgNo))
   IF dustindex LT 0 THEN BEGIN
      IF DebugFlag GT 0 THEN $
         CISSCAL_Log,'No dust ring epoch found. Skipping...'
      RETURN
   ENDIF

   dustfile = CalibrationBaseDir + 'dustring/nac_dustring_'+$
              strtrim(string(epochs[dustindex]),2)+'.img'

   drcObj = OBJ_NEW('CassImg')
   drcObj->ReadVic, dustfile, /Quiet, /NotCass
   dustCorr = fltarr(1024,1024)
   dustCorr = drcObj->Image() 
   OBJ_DESTROY, drcObj          ; Finished with object: reclaim the space

; remove folder info from dustfile string:
   lastslash = strpos(dustfile,'/',/reverse_search)
   dustfile = strmid(dustfile,lastslash+1)
   
; now correct ring at sample=887, line=388 for A/B = OFF images:
   dustfile2 = ''

   IF self.ABFlag eq 'OFF' THEN BEGIN
      dustfile2 = CalibrationBaseDir + 'dustring/nac_dustring_aboff.img'
      
      drcObj2 = OBJ_NEW('CassImg')
      drcObj2->ReadVic, dustfile2, /Quiet, /NotCass
      dustCorr2 = fltarr(1024,1024)
      dustCorr2 = drcObj2->Image() 
      OBJ_DESTROY, drcObj2      ; Finished with object: reclaim the space

      lastslash = strpos(dustfile2,'/',/reverse_search)
      dustfile2 = strmid(dustfile2,lastslash+1)
      
      dustCorr = dustCorr * dustCorr2
   ENDIF
   
   IF DebugFlag gt 0 THEN BEGIN
      CISSCAL_Log,'Performing NAC dust ring correction:'
      CISSCAL_Log,'  Dust ring file = ',dustfile
      IF dustfile2 ne '' then CISSCAL_Log,'  Dust ring file = ',dustfile2
   ENDIF   

   sum = self.Labels -> Get('INSTRUMENT_MODE_ID')   

   if sum eq 'SUM2' then dustCorr = rebin(dustCorr, 512,512)
   if sum eq 'SUM4' then dustCorr = rebin(dustCorr, 256,256)
   
   *self.ImageP = *self.ImageP * dustCorr

;------------------------------------------------------
; Mottling correction for images after sclk=1444733393:
;    (same as 2003-286T10:28:04; pre-SOI)
;------------------------------------------------------

   mottlefile = ''

   IF self.ImgNo ge 1444733393L THEN BEGIN
      
      mottlefile = 'nac_mottle_1444733393.img'

      motObj = OBJ_NEW('CassImg')
      motObj->ReadVic, CalibrationBaseDir + 'dustring/' + mottlefile, /Quiet, /NotCass
      mottle = fltarr(1024,1024)
      mottle = motObj->Image() 
      OBJ_DESTROY, motObj      ; Finished with object: reclaim the space

      IF DebugFlag gt 0 THEN BEGIN
;       CISSCAL_Log
         CISSCAL_Log,'Performing NAC mottling correction:'
         CISSCAL_Log,'  Mottle file = ',mottlefile
      ENDIF

; rebin for summed images:
      if sum eq 'SUM2' then mottle = rebin(mottle, 512,512)
      if sum eq 'SUM4' then mottle = rebin(mottle, 256,256)

   ; determine strength factor; need effective wavelength of filter

      Filter1 = self.Filter1
      Filter2 = self.Filter2
      if ((Filter1 eq 'CL1') or (Filter1 eq 'P0') or (Filter1 eq 'P60') or $
          (Filter1 eq 'P120') or (Filter1 eq 'IRP0')) and Filter2 eq 'CL2' then Filter1 = 'CLR'
      
      filters = ['UV1','UV2','UV3','BL1','BL2','GRN','RED','IR1','IR2','IR3','IR4',$
                 'CB1','CB2','CB3','MT1','MT2','MT3','CLR']
      sfacts = [1.199,1.186,1.069,1.00,0.833,0.890,0.843,0.997,0.897,0.505,0.780,0.764,$
                0.781,0.608,0.789,0.722,0.546,0.763]

      sfindex = where((filters eq Filter1) or (filters eq Filter2),nfound)
      IF nfound eq 1 THEN begin
         sfact = sfacts[sfindex[0]]
      ENDIF ELSE begin
       ; use effective wavelength to estimate strength factor:
         effwl = ''
         GET_LUN, DBFile
         OPENR, DBFile, CalibrationBaseDir + 'efficiency/na_effwl.tab', ERROR=err
         IF ( err NE 0 ) THEN BEGIN
            If DebugFlag gt 0 THEN CISSCAL_Log, '  Effective wavelength database not found; ' + $
                                                'using strength factor of 1.0'
            sfact = 1.0
         ENDIF ELSE BEGIN
            while not eof(DBFile) do begin
               text=''
               readf, DBFile, text
               if strpos(text, '\begindata') ge 0 then break
            endwhile
          
            WHILE ( (effwl EQ '') AND (NOT EOF(DBFile))) DO BEGIN
;       Keep looking...
               LineBuf=''
               READF, DBFile, LineBuf
               LineBuf = STRCOMPRESS(LineBuf)        ; collapse whitespace to single spaces
               Fields = STRSPLIT(LineBuf,' ',/extract) ; tokenize
               IF Fields[0] NE '' THEN BEGIN           ; have tokens OK...
                  IF (( Fields[0] EQ Filter1 ) $
                      AND ( Fields[1] EQ Filter2 )) THEN effwl = Fields[4]
               ENDIF
            ENDWHILE
            IF effwl EQ '' THEN BEGIN
;       Couldn't find a match in the database
               If DebugFlag eq 2 THEN BEGIN
                  CISSCAL_Log, '  Mottle correction: effective wavelength database contained ' + $
                               'no factor for filter combination:', $
                               self.Instrument + ':' + Filter1 + ':' + Filter2
                  CISSCAL_Log, '  Using strength factor of 1.0'
               ENDIF
               sfact = 1.0
            ENDIF ELSE BEGIN
               effwl = float(effwl)
               sfact = 1.30280 - 0.000717552 * effwl
               IF DebugFlag gt 0 THEN CISSCAL_Log,'  Strength factor = ' + strtrim(string(sfact),2) 
            ENDELSE
         ENDELSE
         FREE_LUN,DBFile
      ENDELSE
      
      *self.ImageP = *self.ImageP * (1l - sfact*mottle/1000.)
      
   ENDIF

;	Update calibration history in image label:
;		(added by Ben Knowles, 11/04)
;               (revamped for CISSCAL 3.7, 5/13)

   if mottlefile ne '' and dustfile2 ne '' then $
      ffname = dustfile + '; ' + dustfile2 + '; ' + mottlefile else $
         if mottlefile ne '' then ffname = dustfile + '; ' + mottlefile else $
            ffname = dustfile

   junk=self.Labels->Set('FLAT_FIELD_FILE_NAME',ffname,1,/new)

ENDIF

END
