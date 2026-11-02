;;	cassimg__writevic.pro
;;	Procedure to write out this CassImg object as a VICAR file
;;	Kevin	10/9/98

PRO CassImg::WriteVic, FileName, imagetype=imagetype,dark=dark,pol=pol
@cisscal_common.pro	; include COMMON definitions

;	N.B. Watch out for mismatches between the contents of the
;	associative array in our Labels subobject and the instance
;	variables we have for convenience!

;	If no file selected:
  IF N_PARAMS() LT 1 or file_test(FileName,/dir) or FileName eq '' THEN BEGIN
      IF DebugFlag gt 0 THEN CISSCAL_Log,'  No output filename specified'
      RETURN
  ENDIF

;	Currently we will always write the image as REAL
  IF NOT keyword_set(imagetype) THEN BEGIN
      IF keyword_set(dark) THEN BEGIN
         WriteBuff = dark
      ENDIF ELSE IF keyword_set(pol) THEN BEGIN ; added pol keyword for version 3.7 to work 
                                                ; with make_polar_image - BK 8/28/2013
         WriteBuff = pol
      ENDIF ELSE BEGIN
          IF NOT PTR_VALID(self.ImageP) THEN BEGIN
              IF DebugFlag gt 0 THEN $
                 CISSCAL_Log,'  No image pixels found; file not written'
              RETURN
          ENDIF
          WriteBuff = FLOAT(*self.ImageP)
          if PTR_VALID(self.MissingP) then begin ;replace missing pixels
             wmiss = where(*self.MissingP,nmiss)
             if nmiss gt 0 then WriteBuff[wmiss] = (*(*CalOptions).defval).missing
          endif

          if PTR_VALID(self.saturatedP) then begin ; replace saturated pixels
             ; if default value set to !values.f_infinity, leave as-is
             if (*(*CalOptions).defval).saturated ne !values.f_infinity then begin 
                wsat = where(*self.saturatedP,nsat)
                if nsat gt 0 then WriteBuff[wsat] = (*(*CalOptions).defval).saturated
             endif
          endif

      ENDELSE
  ENDIF ELSE IF imagetype eq 'mask' THEN BEGIN
      IF NOT PTR_VALID(self.MaskP) THEN BEGIN
          IF DebugFlag gt 0 THEN CISSCAL_Log,'  No mask pixels found; file not written'
          RETURN
      ENDIF
      WriteBuff= FLOAT(*self.maskP)
  ENDIF ELSE IF imagetype eq 'saturated' THEN BEGIN
      IF NOT PTR_VALID(self.SaturatedP) THEN BEGIN
          IF DebugFlag gt 0 THEN CISSCAL_Log,'  No saturated pixels found; file not written'
          RETURN
      ENDIF
      WriteBuff= FLOAT(*self.saturatedP)
  ENDIF ELSE IF imagetype eq 'missing' THEN BEGIN
      IF NOT PTR_VALID(self.MissingP) THEN BEGIN
          IF DebugFlag gt 0 THEN CISSCAL_Log,'  No missing pixels found; file not written'
          RETURN
      ENDIF
      WriteBuff= FLOAT(*self.missingP)
  ENDIF

;	open file for writing and set error handling
  
  OPENW,ilun,FileName,/get_lun
  IF DebugFlag gt 0 THEN CISSCAL_Log,$
    '  Output VICAR image file opened: ', FileName
  ON_IOERROR, writefailed

;	Modify or add to labels
  Junk = self.Labels->Set('DAT_TIM', SYSTIME(0), 1)
  
  self.VicFormat = 'REAL'
  Junk = self.Labels->Set('FORMAT', 'REAL', 1)


;	Determine our REAL format
  CASE STRUPCASE(!version.arch) OF
      'VAX':	BEGIN
          ThisHost = 'VAX_VMS'
          self.VicRealFmt = 'VAX'
      END
      'ALPHA':	BEGIN
          ThisHost = 'DECSTATN'
          self.VicRealFmt = 'RIEEE'
      END
      'X86':	BEGIN
          ThisHost = 'PC_X86'
          self.VicRealFmt = 'RIEEE'
      END
      'X86_64':	BEGIN
          ThisHost = 'PC_X86_64'
          self.VicRealFmt = 'RIEEE'
      END
      'SPARC':	BEGIN
          ThisHost = 'SUN-4'
          self.VicRealFmt = 'IEEE'
      END
      'MIPSEB':	BEGIN
          ThisHost = 'SGI'
          self.VicRealFmt = 'IEEE'
      END
      'IBMR2':	BEGIN
          ThisHost = 'IBMR2'
          self.VicRealFmt = 'IEEE'
      END
      'PPC':    BEGIN
          ThisHost = 'PPC'
          self.VicRealFmt = 'RIEEE'
      END
      'I386':    BEGIN
          ThisHost = 'i386'
          self.VicRealFmt = 'RIEEE'
      END
      ELSE: BEGIN
          IF DebugFlag gt 0 THEN CISSCAL_Log,$
            "  Can't write float file: can't recognise host architecture"
          RETURN
      END
  ENDCASE
  ThisIntFmt = LocalIntFmt()

;	Update host/format labels appropriately
  Junk = self.Labels->Set('REALFMT', self.VicRealFmt, 1)
  Junk = self.Labels->Set('BREALFMT', self.VicRealFmt, 1)
  Junk = self.Labels->Set('HOST', ThisHost, 1)
  Junk = self.Labels->Set('BHOST', ThisHost, 1)
  Junk = self.Labels->Set('INTFMT', ThisIntFmt, 1)
  Junk = self.Labels->Set('BINTFMT', ThisIntFmt, 1)

;	We will just write all the labels followed by binary header
;	and image - no binary prefix, no trailing (EOL) labels.
;       Therefore temporarily change these labels and RECSIZE appropriately
  if keyword_set(dark) or keyword_set(pol) or keyword_set(imagetype) then begin
     oldnlb = self.NLB
     Junk = self.Labels->Set('NLB', 0, 0)   ; no binary header
  endif

  oldrecsize = self.RecSize
  newrecsize = self.NS * 4
  Junk = self.Labels->Set('RECSIZE', newrecsize, 0) ; Each sample has a 4-byte REAL value

  oldnbb = self.NBB
  Junk = self.Labels->Set('NBB', 0, 0)
  oldeol = self.Labels->Get('EOL')
  Junk = self.Labels->Set('EOL', 0, 0)
  
;	LBLSIZE must be a multiple of RECSIZE
;	Now done automatically inside self.Labels->toString()
;	Get our label object to serialise itself, then write it and
;		pack to the announced size
  LabelText = self.Labels->toString(dark=dark)
  LabelSize = self.Labels->Get('LBLSIZE')

  WRITEU,ilun, LabelText
  WRITEU,ilun, BYTARR(LabelSize - STRLEN(LabelText))
 
;       Write binary header if not a dark or pol file
  if not keyword_set(dark) and not keyword_set(pol) then begin
     if self.NLB gt 0 and ptr_valid(self.BinaryHdrP) then begin 
        BinaryHdr = bytarr(newrecsize, self.NLB)   ; scale to new recsize
        BinaryHdr[0:oldrecsize-1,*] = *self.BinaryHdrP
        WRITEU,ilun,BinaryHdr
     endif
  endif

;	Write image in real format
  IF DebugFlag gt 0 THEN CISSCAL_Log, '  Writing as real format'
  WRITEU,ilun,WriteBuff

  CLOSE,ilun
  free_lun,ilun

;       Reset labels to original values
  IF keyword_set(dark) or keyword_set(pol) or keyword_set(imagetype) then begin
     Junk = self.Labels->Set('NLB', oldnlb, 0)
  ENDIF

  Junk = self.Labels->Set('RECSIZE', oldrecsize, 0)
  Junk = self.Labels->Set('NBB', oldnbb, 0)
  Junk = self.Labels->Set('EOL', oldeol, 0)

  IF DebugFlag gt 1 THEN CISSCAL_Log,$
    '  Output VICAR image file closed: ', FileName
  RETURN

;	Handle I/O errors here ourselves
writefailed:
  IF DebugFlag gt 0 THEN CISSCAL_Log, '  Write failed: ' + !ERR_STRING
  IF DebugFlag gt 1 THEN CISSCAL_Log, '  fstat =', fstat(ilun)
  
  close,ilun
  free_lun,ilun

END
