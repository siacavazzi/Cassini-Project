;;	cisscal.pro
;;	Top level wrapper for IDL Cassini Image Calibration suite
;;	Kevin	July 1999, et seq.
;;

;	Note that this runs as an "immediate" or batch script rather
;	 than compiling anything.
;	Thus you can type at the system prompt:
;		idl cisscal
;	If you are already at an IDL prompt, you will instead need to use
;		@ cisscal

;PRO CISSCal

;	Basically just need to run the GUI
;	 after picking up path to CISSCAL code
;	 if one is given in the environment variable CisscalDir

@cisscal_common.pro ;include COMMON definitions

EnvVar = GETENV('CisscalDir')
IF EnvVar NE '' THEN CisscalDir = EnvVar
!PATH = !PATH + ':' + CisscalDir
IF STRMID(CisscalDir, STRLEN(CisscalDir)-1, 1) NE '/' THEN $
	CisscalDir = CisscalDir + '/'

EnvVar = GETENV('CalibrationBaseDir')
IF EnvVar NE '' THEN CalibrationBaseDir = EnvVar
IF STRMID(CalibrationBaseDir, STRLEN(CalibrationBaseDir)-1, 1) NE '/' THEN $
	CalibrationBaseDir = CalibrationBaseDir + '/'

EnvVar = GETENV('ImageBaseDir')
IF EnvVar NE '' THEN ImageBaseDir = EnvVar

CISSCal_Gui

;END
