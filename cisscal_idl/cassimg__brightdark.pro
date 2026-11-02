;;	cassimg__brightdark.pro
;;	Correct image for Bright/Dark pairs
;;	Kevin	14th August 1998
;;      Daren 2003 - added algorithm: replace pixel with median of neighbors

PRO CassImg::BrightDark

;	This need only be done in anti-blooming mode, where
;	adjacent pairs of pixels transfer charge leading to
;	one being overbright and its neighbour underbright
;
;;;;;;   ONE PARAMETER FROM GUI NEEDED:
;;;;;;    thresh = (*(*(*CalOptions).abpp).imagemean).threshold
;;;;;;    good default value is 30
;;;;;;    25 is lowest i'd ever go for production work
;;;;;;    50 is much more conservative default, will catch all the "obvious" b/d pairs

@cisscal_common.pro	; include COMMON definitions

thresh = (*(*CalOptions).abpp).threshold

IF DebugFlag gt 0 THEN BEGIN
;   CISSCAL_Log
   CISSCAL_Log,'Removing anti-blooming pixel pairs:' 
ENDIF

IF ( self.AbFlag EQ 'ON' ) THEN BEGIN
    IF DebugFlag gt 0 THEN BEGIN
        CISSCAL_Log, '  Antiblooming mode is ON...'
    ENDIF
ENDIF ELSE BEGIN
    IF DebugFlag gt 0 THEN CISSCAL_Log, '  Antiblooming mode is OFF; No Bright/Dark correction required'
    RETURN
ENDELSE

IF NOT (self.InstModID EQ 'FULL') THEN BEGIN
    IF DebugFlag gt 0 THEN CISSCAL_Log, '  Not in FULL summation mode; Skipping Bright/Dark correction'
    RETURN
ENDIF

img = *self.ImageP
	
; detect darks:  any pixel more than bad_thresh below its three neighbors
; and its left and right neighbors are similar in value
bad1 = img lt (shift(img, 1,0) - thresh)
bad2 = img lt (shift(img, -1,0) - thresh)
bad3 = img lt (shift(img,0,1) - thresh)
darks = bad1*bad2*bad3
ndarks=total(darks)

	; detect brights - similar to darks but opposite logic
bad1 = img gt (shift(img, 1,0) + thresh)
bad2 = img gt (shift(img, -1,0) + thresh)
bad3 = img gt (shift(img,0, -1) + thresh)
brights = bad1*bad2*bad3
nbrights=total(brights)

; find br/dark pairs - wherer a bright sits right above a dark
bad = shift(brights,0,-1) and darks      ; find darks that have brights above
nbad = total(bad)

; spread bad locations upward to cover the bright partner of every dark
bad = (bad + shift(bad, 0, 1)) gt 0

mim = 0.5*( shift(img,-1,0) + shift(img,1,0)) ; average of horizontal neighbors

*self.ImageP = (1-bad)*img + bad*mim
IF DebugFlag gt 0 THEN CISSCAL_Log,  '  Found '+strtrim(string(ndarks),2)+' darks,  ' + strtrim(string(nbrights),2) +' brights,  and '+strtrim(string(nbad),2)+' bright/dark pairs'

;	Update calibration history in image label:
;	       (added by Ben Knowles, 4/02)
;              (revised by Daren Wilson, dec. 2003)
;              (revamped for CISSCAL 3.7, 4/13)

junk=self.Labels->Set('AB_PIXEL_CORRECTION_FLAG',1,0,/new)

END











