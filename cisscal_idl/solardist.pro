FUNCTION SolarDist, Body, YearFrac
@cisscal_common.pro	; include COMMON definitions

; Changes made on 3/14/08 by BK:
;  - made standalone 
;  - replaced hardcoded values with 'solardist_*' files
;    containing target-sun distances from 2000 through 2015:
; Updated on 8/1/2018 by BK:
;  - extended through EOM!
  
IF Body EQ 'JUPITER' THEN BEGIN
    cisscal_readspec,CisscalDir + 'solardist_jup.txt',tmp,JupDist,npts,/noheader
    RETURN, INTERPOLATE(JupDist, (YearFrac-2000.0)*10.0)
ENDIF ELSE IF Body EQ 'SATURN' THEN BEGIN
    cisscal_readspec,CisscalDir + 'solardist_sat.txt',tmp,SatDist,npts,/noheader
    RETURN, INTERPOLATE(SatDist, (YearFrac-2000.0)*10.0)
ENDIF ELSE BEGIN
  IF DebugFlag gt 0 THEN CISSCAL_Log, 'Cannot understand I/F target parameter: ', Body
  RETURN, 0
ENDELSE

END
