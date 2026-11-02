;;	cassimg__linearise.pro
;;
;;	Method to correct image for non-linearity
;;	 Kevin Beurle	   17th September 1998
;;      Edited by:
;;	 Ben Knowles       28th December 2003

PRO CassImg::Linearise

@cisscal_common.pro	; include COMMON definitions

;	Algorithm from WAC/NAC CALIBRATION RESULTS: Nonlinear response terms
;	documents by Bob West and Charlie Avis

;	These are the correction factor tables from the referenced documents
;	For each gain state there are a list of DNs where measurements
;	  were performed and the corresponding correction factors C
;	The correction is then performed as DN'=DN*Cdn
;	Where Cdn is an interpolation for C from the tabulated values

;	For ease of interpolation, I have included a value of C for DN=0
;	by duplicating the correction factor for the lowest measured DN

;	WAC tables for gains 0, 1, 2, 3
  WAC0 = [[	   0.0,   55.3,  153.5,  250.7,  300.5,  694.9, 1167.7, $
		1472.7, 1805.8, 2430.6, 2844.5, 3405.9, 4096.0 ], $
	[	 0.885,  0.885,  0.957,  0.976,  0.977, 0.986,  1.006, $
		 0.997,  0.976,  1.047,  1.101,  1.092, 1.168 ]]

  WAC1 = [[	   0.0,   30.3,  182.4,  257.6,  359.6,  765.0, 1118.5, $
		1619.2, 1917.9, 2312.8, 2803.6, 3384.3, 4096.0 ], $
	[	 0.839,  0.839,  0.977,  0.988,  0.991,  0.998, 1.001, $
		 1.006,  1.009,  1.012,  1.017,  1.023, 1.029 ]]

  WAC2 = [[	   0.0,   21.8,  121.2,  240.3,  320.1,  598.8, 1034.9, $
		1509.9, 1827.8, 2219.6, 2687.7, 3231.7, 3902.4, 4096.0 ], $
	[	 0.915,  0.915,  0.985,  0.994,  0.995,  0.997,  1.000, $
		 1.002,  1.002,  1.004,  1.007,  1.010,  1.020,  1.020 ]]

  WAC3 = [[	   0.0,   47.2,  131.4,  256.5,  340.8,  760.7, 1012.1, $
		1514.2, 1848.6, 2183.0, 2681.0, 3177.4, 3830.6, 4096.0 ], $
	[	 0.895,  0.895,  0.965,  0.989,  0.992,  1.000,  1.002, $
		 1.005,  1.006,  1.007,  1.009,  1.011,  1.015,  1.016 ]]


;	NAC tables for gains 0, 1, 2, 3
  NAC0 = [[	   0.0,   75.0,  221.7,  294.2,  366.6,  440.4,  855.1, $
		1351.2, 1522.0, 1766.9, 2012.0, 2288.3, 2819.3, 3496.7, $
		4096.0 ], $
	[	 0.958,  0.958,  0.972,  0.977,  0.980,  0.979,  1.008, $
		 0.957,  0.944,  0.976,  1.071,  1.130,  1.121,  1.068, $
		1.080 ]]

  NAC1 = [[	   0.0,  121.4,  200.3,  281.1,  401.4,  801.9, 1201.5, $
		1439.5, 1755.4, 2068.9, 2534.9, 2997.4, 3603.9, 4096.0 ], $
	[	 0.987,  0.987,  0.997,  0.995,  0.995,  0.996,  0.997, $
		 0.999,  1.001,  1.004,  1.008,  1.013,  1.020,  1.024 ]]

  NAC2 = [[	   0.0,   34.8,  102.7,  203.3,  272.0,  407.8,  815.1, $
		1221.9, 1493.0, 1757.1, 2165.0, 2565.4, 3092.6, 3741.8, $
		4096.0 ], $
	[	 0.974,  0.974,  0.990,  1.000,  0.997,  0.997,  0.998, $
		 0.998,  0.999,  1.003,  1.002,  1.004,  1.008,  1.014, $
		1.017 ]]

  NAC3 = [[	   0.0,   71.6,  212.7,  282.8,  354.0,  423.4,  849.8, $
		1273.8, 1415.4, 1697.5, 2118.3, 2537.5, 3091.9, 3640.4, $
		4096.0 ], $
	[	 0.986,  0.986,  0.997,  0.999,  0.998,  1.001,  0.998, $
		 0.998,  0.998,  0.999,  1.001,  1.002,  1.005,  1.009, $
		1.011 ]]

Instrument = (self.Labels->Get('INSTRUMENT_ID'))[0]
TblToUse = 0

IF DebugFlag gt 0 THEN BEGIN
   CISSCAL_Log, 'Correcting for nonlinearity...'
ENDIF


  CASE Instrument OF
   'ISSNA': CASE self.GainState OF
	0:	TblToUse = NAC0
	1:	TblToUse = NAC1
	2:	TblToUse = NAC2
	3:	TblToUse = NAC3
    ENDCASE
   'ISSWA': CASE self.GainState OF
	0:	TblToUse = WAC0
	1:	TblToUse = WAC1
	2:	TblToUse = WAC2
	3:	TblToUse = WAC3
    ENDCASE
  ENDCASE

  IF N_ELEMENTS(TblToUse) EQ 1 THEN BEGIN
      IF DebugFlag gt 0 THEN BEGIN
          CISSCAL_Log, '  Unexpected instrumentID/gain state: ', Instrument, self.GainState
          CISSCAL_Log, '  Skipping linearity correction'
      ENDIF
      RETURN
  ENDIF

  IF DebugFlag eq 2 THEN BEGIN
     CISSCAL_Log, '  Table in use:', TblToUse
  ENDIF

;	Easiest way is probably to construct a lookup table so only
;	need to interpolate once for each DN (integer) value
;	ASSUMPTION: C will not change significantly over fractional DN
;	If this is not the case, then can perform simple second interpolation
;	between DNs while mapping LUT onto the image
  DN_VALS = TblToUse[*,0]
  C_VALS = TblToUse[*,1]
  C_LUT = INTERPOL(C_VALS, DN_VALS, INDGEN(4096))

;	Map LUT onto image, defending against out-of-range DN values
  IndexImage = FIX(*self.imagep)
  IndexImage = ( IndexImage > 0 ) < 4095	; Trim lookup DN to [0, 4095]
  C_ARRAY = C_LUT[ IndexImage ]

;  DebugFlag=1
  IF DebugFlag eq 2 THEN BEGIN
	InRange = [ MIN(IndexImage), MAX(IndexImage) ]
	CsUsed = C_LUT[InRange[0]:InRange[1]]
        CISSCAL_Log, '  Img range now is ' + STRING(InRange[0]) + ' to ' + STRING(InRange[1])
        CISSCAL_Log, '  through which LUT varies from' + STRING(MIN(CsUsed)) +  ' to ' + STRING(MAX(CsUsed))
  ENDIF

  NonLinImg = *self.ImageP
  LinImg = NonLinImg * C_ARRAY
  *self.ImageP = LinImg
  TempImg = LinImg - NonLinImg

  IF DebugFlag eq 2 THEN BEGIN
      CISSCAL_Log, '  DN changes were between: ' + STRING(MIN(TempImg)) + ' and ' + STRING(Max(TempImg))
      CISSCAL_Log, '  Img range now is ' + STRING(MIN(*self.ImageP)) + ' to ' + STRING(MAX(*self.ImageP))
  ENDIF

;	Update calibration history in image label:
;		(added by Ben Knowles, 4/02)
;               (revamped for CISSCAL 3.7, 5/13)

junk=self.Labels->Set('NONLINEARITY_CORRECTION_FLAG',1,0,/new)

END
