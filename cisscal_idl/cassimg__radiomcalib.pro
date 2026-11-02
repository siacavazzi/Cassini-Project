;;	cassimg__radiomcalib.pro
;;	Toplevel method definition of Cassini image calibration algorithm
;;	Kevin	12th Aug 1998 and various
;;      Doug Dawson 6th Sep 2000
;;
;;	Method for Radiometric Calibration of a Cassini image
;;	This follows the steps outlined in
;;		Cassini ISS Image Calibration: Theoretical Basis
;;		[ R.West, draft version of 14th July 1991 ]
;;	to calibrate an image from "raw" DNs to intensity or I/F
;;	Modified 30/12/1998 to use steps as defined in calibration document
;;      Modified 6/9/2000 to fit slope-file version
;;	Logging mechanism modified 8th Nov 2000
;;	Modified 4/5/2002 by Ben Knowles to add calibration history to 
;;		image headers, and send dark subtraction options to 
;;		cassimg__subtractdark.pro		

PRO CassImg::RadiomCalib, CancelFlag=CancelFlag

;	This is a sequencing method which invokes methods for each
;	step in turn
;
;	The calibration data needed at various stages depend
;	on the settings (filters, exposure,..) when the image was
;	taken. These are described by keywords in the VICAR format
;	image file.
;
;	The Object-oriented features of IDL 5.x are used to
;	encapsulate these details along with the actual image,
;	thus methods act on the image objects to "make them
;	calibrate themselves" according to their internal data.

@cisscal_common.pro	; include COMMON definitions

;	Mustn't apply calibration more than once to an image object!
;	Our "Calibrated" field should be zero if object is as yet uncalibrated
;	In fact, we will set this property to the number of each step we reach

CancelFlag = 0
  
IF self.Calibrated NE 0 THEN BEGIN
    IF DebugFlag gt 0 THEN BEGIN
        CISSCAL_Log 
        CISSCAL_Log, '**'
        CISSCAL_Log, '** Image already calibrated: calibration stage flag = ' + $
                     strtrim(string(self.Calibrated),2)
        CISSCAL_Log, '**'
    ENDIF
    
    message=['Image already calibrated; calibration stage flag = ' + $
             strtrim(string(self.Calibrated),2),$
             'Would you like to resume calibration at the next calibration stage?']

    if IBatch ge 0 then begin  ; batch mode, add "cancel" button
       answer = dialog_message(message, /cancel, /default_cancel,$
                               dialog_parent=GuiBase, /question)  
    endif else begin           ; not batch mode
       answer = dialog_message(message, dialog_parent=GuiBase, /default_no, /question)
    endelse
       
    if answer ne 'Yes' then begin
       if answer eq 'No' then CancelFlag = 1
       if answer eq 'Cancel' then CancelFlag = 2
       return
    endif
ENDIF


;**************************

IF DebugFlag gt 0 THEN BEGIN
   CISSCAL_Log
   CISSCAL_Log,'Beginning radiometric calibration...'
   CISSCAL_Log
ENDIF

;	Step 1: Conversion from 8 to 12 bits if 12-to-8 table was used
if (*(*CalOptions).lutc).onoff AND self.Calibrated lt 1 then begin
	self->TwelveBit	
	self.Calibrated = 1
endif

;	Step 2: Correction for uneven bit weighting
;		(using table appropriate for the gain state)
if (*(*CalOptions).bitw).onoff AND self.Calibrated lt 2 then begin
	self->BitWeightCorrect
	self.Calibrated = 2
endif

;	Step 3: Bias subtraction
if(*(*CalOptions).bias).onoff AND self.Calibrated lt 3 then begin
  	self->DeBias
	self.Calibrated = 3
endif

;	Step 4: Subtraction of 2-hz noise
if(*(*CalOptions).twohz).onoff AND self.Calibrated lt 4 then begin
	self->TwoHz
	self.Calibrated = 4
endif

;       Step 5: Subtraction of appropriate dark frame
if (*(*CalOptions).dark).onoff AND self.Calibrated lt 5 then begin
	self->SubtractDark
	self.Calibrated = 5
endif

;	Step 6: Correct for bright/dark differences in antiblooming mode
;		(depends on antiblooming mode)
if (*(*CalOptions).abpp).onoff AND self.Calibrated lt 6 then begin
	self->BrightDark          ;THIS NEEDS WORK
	self.Calibrated = 6
endif	

;	Step 7 Correct for nonlinearity
;		(depends on gain state)
if (*(*CalOptions).lin).onoff AND self.Calibrated lt 7 then begin
	self->Linearise			; Do this regardless of gainstate
	self.Calibrated = 7
endif

;	Step 8: Flat field correction
if (*(*CalOptions).flat).onoff AND self.Calibrated lt 8 then begin
;       Divide by flatfield
    self->DivideByFlats
;	Correct for dust ring(s) and mottling effects
    self->DustRingCorrect
    self.Calibrated = 8
endif

;CONVERT TO FLUX:
;	Step 9: Convert to Flux
if (*(*CalOptions).flux).onoff AND self.Calibrated lt 9 then begin
    if (*(*(*CalOptions).flux).ioverf).onoff or (*(*CalOptions).flux).gain_onoff then $
       self->DNtoElectrons      ; multiply by gain factor
    if (*(*(*CalOptions).flux).ioverf).onoff or (*(*CalOptions).flux).expt_onoff then $
       self->DivideByExpoT      ; divide by exp time, correcting for shutter offset
    if (*(*(*CalOptions).flux).ioverf).onoff or (*(*CalOptions).flux).opta_onoff then $
       self->DivideByAreaPixel  ; divide by optics area and solid angle
    if (*(*(*CalOptions).flux).ioverf).onoff or (*(*CalOptions).flux).tran_onoff then $
       self->DivideByEfficiency ; divide by T0*T1*T2*QE summed over passband
    self.Calibrated = 9
endif

;       Step 10: Absolute Correction Factors and Sensitivity vs. Time
if (*(*CalOptions).corr).onoff AND self.Calibrated lt 10 then begin
   self->CorrectionFactors      ; divide by fudge factors
   if (*(*CalOptions).corr).time then $
      self->SensVsTime          ; correct for sensitivity decline over time
   self.Calibrated = 10
endif

;	Step 11: Apply geometric correction if required
if (*(*CalOptions).geom).onoff AND self.Calibrated lt 11 then begin
   self->GeomCorr
   self.Calibrated = 11
endif

;	Add CALIBRATION_STAGE keyword to image header:
junk=self.Labels->Set('CALIBRATION_STAGE',strtrim(string(self.Calibrated),2),1,/new)

IF DebugFlag gt 0 THEN BEGIN
   CISSCAL_Log
   CISSCAL_Log, 'Image calibration complete.'
ENDIF

END
