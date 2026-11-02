;;	cassimg__define.pro
;;	Package defining CassImg objects and access methods
;;	Kevin Beurle	8th September 1998

;	A CassImg object contains a Cassini image and related information
;	The ImageP member is a pointer to the image itself
;		(which is a 2D array of pixel values)
;	The OtherP member is a pointer to the "Binary prefix" data
;		(also a 2D array of values, 24 bytes per image line)
;	There are also members describing the image parameters
;		which are set up from the labels read with the image

;	CassImg::Image()
;	Access function returning a copy of the image array
FUNCTION CassImg::Image
@cisscal_common.pro	; include COMMON definitions
;	Bail out if no data available
  imbuff = 0
  IF ((self.NS EQ 0) OR (self.NL EQ 0)) THEN BEGIN
      IF DebugFlag gt 0 THEN CISSCAL_Log, $
        'No valid image size [samples,lines]: [', self.NS, self.NL, ']'
  ENDIF ELSE IF NOT PTR_VALID(self.ImageP) THEN BEGIN
      IF DebugFlag gt 0 THEN CISSCAL_Log, 'No valid image pointer'
  ENDIF ELSE BEGIN
      imbuff = INTARR(self.NS, self.NL)
      imbuff = *self.ImageP
  ENDELSE
  RETURN,imbuff
END

;	CassImg::Other()
;	Access function returning a copy of the "binary prefix array"
FUNCTION CassImg::Other

;	Bail out if no data available
  IF ((self.NBB EQ 0) OR (self.NL EQ 0)) THEN RETURN,0
  IF NOT PTR_VALID(self.OtherP) THEN RETURN, 0
;	otherwise return the data
  OtherBuff = INTARR(self.NBB, self.NL)
  OtherBuff = *self.OtherP
  RETURN, OtherBuff
END

;	CassImg::Overclocks()
;	Access function returning a copy of the overclocked pixel values
FUNCTION CassImg::Overclocks

;	Bail out if NL is 0
  IF (self.NL EQ 0) THEN RETURN, 0
;	Return a zero vector if no overclocks available,
;	 otherwise return a copy of the vector of overclocks
  OverClkBuff = INTARR(self.NL)
  IF PTR_VALID(self.OverClkP) THEN OverClkBuff = FIX(*self.OverClkP)
  RETURN, OverClkBuff
END

;	CassImg::OverclockAvg()
;	Access function returning line-averaged overclocked pixel values
FUNCTION CassImg::OverclockAvg

;	Bail out if NL is 0
IF (self.NL EQ 0) THEN RETURN, 0
;	Return a zero vector if no overclocks available,
;	 otherwise return a copy of the vector of overclocks
OverClkBuff = INTARR(self.NL)
IF PTR_VALID(self.OverClkP) THEN OverClkBuff = FIX(*self.OverClkP)

; get summation mode:
sum = self.Labels -> Get('INSTRUMENT_MODE_ID')

if self.BLType eq 'CAS-ISS2' or self.BLType eq 'CASSINI-ISS' then begin
    OverClkAvg = OverClkBuff[0,*]	
endif else if self.BLType eq 'CAS-ISS3' or $
  self.BLType eq 'CAS-ISS4' then begin
    if sum eq 'FULL' then $
      OverClkAvg = (OverClkBuff[0,*]/2. + OverClkBuff[1,*]/6.)/2.
    if sum eq 'SUM2' then $
      OverClkAvg = (OverClkBuff[0,*] + OverClkBuff[1,*]/3.)/2.
    if sum eq 'SUM4' then $
      OverClkAvg = (OverClkBuff[0,*] + OverClkBuff[1,*])/2.
endif

RETURN, OverClkAvg
END

;	CassImg::Saturated()
;	Access function returning a copy of the "saturated pixels array"
FUNCTION CassImg::Saturated
;	Bail out if no data available
  IF NOT PTR_VALID(self.SaturatedP) THEN RETURN, 0
;	otherwise return the data
  SaturatedBuff = *self.SaturatedP
  RETURN, SaturatedBuff
END

;	CassImg::Missing()
;	Access function returning a copy of the "missing pixels array"
FUNCTION CassImg::Missing
;	Bail out if no data available
  IF NOT PTR_VALID(self.MissingP) THEN RETURN, 0
;	otherwise return the data
  MissingBuff = *self.MissingP
  RETURN, MissingBuff
END

;	CassImg::Mask()
;	Access function returning a copy of the currently-defined mask array
FUNCTION CassImg::Mask
;	Bail out if no data available
  IF NOT PTR_VALID(self.MaskP) THEN RETURN, 0
;	otherwise return the data
  MaskBuff = *self.MaskP
  RETURN, MaskBuff
END

;	CassImg::Name()
;	Access function returning a copy of the image name (image no. as string)
FUNCTION CassImg::name
  RETURN, STRING(self.ImgNo)
END

;	CassImg::BinaryHdr()
;	Access function returning a copy of the "binary header"
FUNCTION CassImg::BinaryHdr
  BinaryHdr = BYTARR(self.Recsize)
  BinaryHdr = *self.BinaryHdrP
  RETURN, BinaryHdr
END

;	CassImg::LabelArray()
;	Access function returning a [[Key, val], [Key, val]...] array
FUNCTION CassImg::LabelArray
  RETURN, self.Labels->LabelArray()
END

;	CassImg::LabelText()
;	Access function returning label array as a single string
FUNCTION CassImg::LabelText
  RETURN, self.Labels->toString()
END

;	CassImg interfaces for other CassLabels methods
;	CassImg::HaveLabel()
FUNCTION CassImg::HaveLabel, KeyWord
  RETURN, self.Labels->Have(KeyWord)
END

;	CassImg::GetLabel()
FUNCTION CassImg::GetLabel, KeyWord
  RETURN, self.Labels->Get(KeyWord)
END

;       CassImg::GetConvType()
FUNCTION CassImg::GetConvType
  RETURN, self.ConvType
END

;       CassImg::GetOffset()
FUNCTION CassImg::GetOffset
  RETURN, self.Offset
END

;       CassImg::GetCalibrated()
FUNCTION CassImg::GetCalibrated
  RETURN, self.Calibrated
END

;	CassImg::SetLabel()
;	Intentionally no support for /NEW keyword here
FUNCTION CassImg::SetLabel, KeyWord, Value, Quoted
  RETURN, self.Labels->Set(KeyWord, Value, Quoted)
END

;       CassImg::LineBreak() 
;       Return linebreak value (indicating a pause in the image
;       readout and/or change in readout rate) given by cisscal_linetime.
;
;       (Added by Ben Knowles, Oct 2013)

FUNCTION CassImg::LineBreak

  gainstate = self.GainState    ;0,1,2,3
  camera = self.Instrument      ;issna, isswa
  conv = self.ConvType          ;table,12-bit,8lsb
  comp = self.EncType           ;lossless,lossy,notcomp
  sum = self.InstModID          ;full,sum2,sum4
  time = self.ExpDur
  fsw = float(self.Fsw)         ;1.3, 1.4, etc. 
  
  exp = time/1000.        
  
  drf = self.Labels -> Get('DELAYED_READOUT_FLAG')
  if (drf EQ 'NO') then btsm = 0
  if (drf EQ 'YES') then btsm = 1
  
  telem_rate = self.Labels -> Get('INSTRUMENT_DATA_RATE')
  cdsr = 24                     ; assume as default
  
  if (telem_rate GE  60. AND telem_rate LE  61.) then cdsr = 8
  if (telem_rate GE 121. AND telem_rate LE 122.) then cdsr = 16
  if (telem_rate GE 182. AND telem_rate LE 183.) then cdsr = 24
  if (telem_rate GE 243. AND telem_rate LE 244.) then cdsr = 32
  if (telem_rate GE 304. AND telem_rate LE 305.) then cdsr = 40
  if (telem_rate GE 365. AND telem_rate LE 366.) then cdsr = 48
  
  ratio = 1.0
  if (comp NE 'NOTCOMP') then begin
     ratio = self.Labels -> Get('INST_CMPRS_RATIO')
     ratio = float(ratio)
     if ratio eq -1 then $
        ratio = self.Labels -> Get('COMPRESSION_RATIO')
  endif
  
  rate = self.Labels -> Get('INSTRUMENT_DATA_RATE')
  roindex = self.Labels -> Get('READOUT_CYCLE_INDEX')
  
  if ptr_valid(self.BinaryHdrP) then begin
     bh = *self.BinaryHdrP
     roo = bh[50]/32 MOD 2      ; Readout order is the 3rd bit of the 51st byte
  endif else begin
     roo = 0        ; assume to avoid crash on old (pre-CISSCAL 3.7) calibrated images,
  endelse           ; which lack a binary header
  
  time = cisscal_linetime(sum, exp, conv, comp, btsm, cdsr, 0, $
                          ratio=ratio, rdind=roindex, camera=camera, roo=roo, fsw=fsw,$
                          line_break=lbreak)

  RETURN,lbreak
END

;	CassImg::SetMissing()
;	Set missing pixels array from GUI
PRO CassImg::SetMissing, missing

;       Bail out if no image:
  IF ((self.NBB EQ 0) OR (self.NL EQ 0)) THEN RETURN

  IF PTR_VALID(self.MissingP) THEN PTR_FREE,self.MissingP
  self.MissingP = PTR_NEW(missing)
END

;	CassImg::MakeRpt()
;	Utility method for debugging, etc.
;	Returns a string containing a summary of the image parameters
FUNCTION CassImg::MakeRpt
  hk_line = STRING( self.ImgNo, ' ', self.ObsID, ' ', self.InstModID, ' ', $
	LONG(self.ExpDur), ' ', $
	self.GainModID, ' ', 'F1x', ' ', 'F2x', ' ', self.AbFlag, ' ', $
	self.ConvType, ' ', self.EncType, ' ', $
	self.OptT[0], ' ', self.DetT, ' ', self.Filter1, ' ', self.Filter2, ' ', self.MissLns)
  RETURN, hk_line
END

;	CassImg::DNRange()
;	Utility method to return DN extrema of an image
;	Returns a two element array containg [min, max] DN values of image
;	  if keyword /ARRAY is set otherwise it returns a string
FUNCTION CassImg::DNRange, TEXT=text
  IF KEYWORD_SET(ARRAY) THEN $
    RETURN, [ MIN(*self.ImageP) , MAX(*self.ImageP) ]

  DNRange = '[' + STRING(MIN(*self.ImageP)) + ' ' + STRING(MAX(*self.ImageP)) + ' ]'
  RETURN, DNRange
END

;	CassImg::Init()
;	Runs automatically during execution of OBJ_NEW('CassImg')
;	Return TRUE if we're happy, otherwise FALSE
FUNCTION CassImg::Init, Param
@cisscal_common.pro	; include COMMON definitions
  Status = 1                      ; TRUE means we're happy
  IF (N_PARAMS() GT 0) THEN BEGIN
;	Do initialisation based on parameter(s): use it as a filename
      IF DebugFlag gt 0 THEN CISSCAL_Log,$
        'Automatically initialising CassImg object from ' + PARAM
      self->ReadVic,Param,/Quiet
  ENDIF
  IF DebugFlag gt 0 THEN self.ObjDebugLevel = DebugFlag
  RETURN, Status
END

;	CassImg::Cleanup()
;	Runs automatically during OBJ_DESTROY of a CassImg object
PRO CassImg::Cleanup
;	Use this opportunity to release any pointer variables
;		we were using for image/other buffers
  IF self.ObjDebugLevel gt 1 THEN CISSCAL_Log, 'Cleanup for destruction of a CassImg object...'
  IF (PTR_VALID(self.BinaryHdrP)) THEN PTR_FREE,self.BinaryHdrP
  IF (PTR_VALID(self.ImageP)) THEN PTR_FREE,self.ImageP
  IF (PTR_VALID(self.OtherP)) THEN PTR_FREE,self.OtherP
  IF (PTR_VALID(self.OverClkP)) THEN PTR_FREE,self.OverClkP
  IF (PTR_VALID(self.SaturatedP)) THEN PTR_FREE,self.SaturatedP
  IF (PTR_VALID(self.MissingP)) THEN PTR_FREE,self.MissingP
  IF (PTR_VALID(self.MaskP)) THEN PTR_FREE,self.MaskP
  IF OBJ_VALID(self.Labels) THEN OBJ_DESTROY,self.Labels
END


;	CassImg::Define
;	Class structure definition for CassImg objects
PRO CassImg__Define
  tmp = { CassImg, $			; Define the CassImg class structure:
;	Properties intoduced by/for our processing...
	Calibrated: 0, $	; Interlock to prevent reprocessing
	PerSecond: 0, $		; Has it been divided by exposure?
	ObjDebugLevel: 0, $	; Turn object debugging info OFF
;	Properties from the image labels...
	Instrument: '', $		; Which instrument ISSNA/ISSWA
        ImgNo: LONG(0), $		; Image number
	ExpDur: 0.0, $			; Exposure duration
	DetT: 0.0, OptT: fltarr(2), $	; Detector and Optics temperatures
	InstModID: '', $		; Instrument and modes
        ShutModID: '', $                ; Shutter mode ID (NACONLY, WACONLY, BOTSIM)
        ShutStateID: '', $              ; Shutter state ID (ENABLED, DISABLED)
	GainModID: '', $		; Gain mode...
	GainState: 0, $			;  and gain state derived from it
	EncType: '', ConvType: '', $	; Encoding and Conversion types
	LfFlag: '', AbFlag: '', $	; Lightflood and Antiblooming flags
	ClFlag: '', $			; Calibration lamp flag
	Target: '', ObsID: '', $	; Target name and Observation ID
	Filter1: '', Filter2: '', $	; Filters in wheels 1 and 2
	MissLns: 0, $			; Number of Missing lines
	RecSize: 0, $			; Record size used in the file
	LeadIn: 0, $			; Number of bytes of start-of-file labels read
        BLType: '', $                   ; Identifies binary label format (added by BK)
	NL: 0, NS: 0, $			; Image size: No. of Lines and Samples
	NLB: 0, NBB: 0, $		; Size of "prefix" on each line
	VicFormat: '', $		; VICAR format used
	VicIntFmt: '', $		; Integer representation "ENDIAN"-ness
	VicRealFmt: '', $		; Floating point representation style
	Offset: '', $			; Offset (bias level) may be embedded
        Fsw: '', $                      ; Flight software version number
;
;	For structures of unknown size, create pointers here
;	and then use them to reference dynamic structures on the heap
;	BinaryHdrP will be a pointer to a record created on the heap
;	ImageP will be a pointer to an image created on the heap,
;	  typically 1024*1024 but maybe 512*512 or 256*256 (SUM2 or SUM4)
;	OtherP will be a pointer to the "other" image bytes: these are the
;	  "binary prefix" bytes on each line containing e.g. overclocked pixels
	BinaryHdrP: PTR_NEW(), $
	ImageP:PTR_NEW(), ImgBytes:0L, $
	OtherP:PTR_NEW(), $
	OverClkP:PTR_NEW(), $
	SaturatedP:PTR_NEW(), $
	MissingP:PTR_NEW(), $
        MaskP:PTR_NEW(), $
;
;	Finally, include a CassLabels object which we will use
;	 to hold the entire set of labels as a simulated
;	 associative array
	Labels:OBJ_NEW() $
	}
END





