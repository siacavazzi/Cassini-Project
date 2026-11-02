;;	cassimg__dntoelectrons.pro
;;	Multiply image by gain constant g (convert DN to electrons)
;;	Kevin Beurle	13th August 1998

PRO CassImg::DNtoElectrons

@cisscal_common.pro	; include COMMON definitions

IF DebugFlag gt 0 THEN BEGIN
   CISSCAL_Log, 'Converting DN to electrons:'
ENDIF

;	Gain used for an image is documented by the GainModID attribute
;	of the image. Nominal values are as follow:
;	Attribute	Gain	Usual	Nominal Gain
;	Value		state	mode	(e- per DN)
;	'1400K'		0	SUM4	215
;	'400K'		1	SUM2	 95
;	'100K'		2	FULL	 29
;	'40K'		3	FULL	 12

;	Actual gains: amend according to calibration as necessary
; Gain = [ 215, 95, 29, 12 ]

; Ground calibration values (temp-dependent) replaced with gain ratios
; from Fall '03 flight data. More work must be done to determine
; appropriate temp dependence (using optics/detector temp?), since 
; sensor_head_electronics temp returned after C37 is incorrect. 
;                             - Ben Knowles, 11/29/04

IF self.Instrument EQ 'ISSNA' THEN BEGIN
    Gain2 = 30.27
    GainRatios = [0.135386, 0.309569, 1.0, 2.357285]
ENDIF ELSE IF self.Instrument EQ 'ISSWA' THEN BEGIN
    Gain2 = 27.68
    GainRatios = [0.125446, 0.290637, 1.0, 2.360374]
ENDIF ELSE BEGIN
  CISSCAL_Log, '  Unexpected instrument code:',self.Instrument
  RETURN
ENDELSE

GainState = self.GainState
TrueGain = Gain2/GainRatios

IF DebugFlag gt 0 THEN BEGIN
   CISSCAL_Log, '  Gain state is '+strtrim(string(GainState),2)+'; scaling by '+$
                strtrim(string(TrueGain[GainState]),2)+' electrons/DN'
ENDIF
IF DebugFlag eq 2 THEN BEGIN
	CISSCAL_Log, '  DN range before scaling is ', MIN(*self.ImageP), ' to ', MAX(*self.ImageP)
ENDIF

*self.ImageP = *self.ImageP * TrueGain[GainState]

IF DebugFlag eq 2 THEN BEGIN
	CISSCAL_Log, '  Img range now is ', MIN(*self.ImageP), ' to ', MAX(*self.ImageP)
ENDIF

;	Update calibration history in image label:
;		(added by Ben Knowles, 4/02)
;               (revamped for CISSCAL 3.7, 5/13)

gaintxt = strtrim(string(TrueGain[GainState],format='(F6.2)'),2) + ' e-/DN'
junk=self.Labels->Set('GAIN_CORRECTION',gaintxt,1,/new)

END
