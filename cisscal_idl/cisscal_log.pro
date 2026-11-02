;;	cisscal_log.pro
;;

PRO CISSCAL_Log, LogThing0, LogThing1, LogThing2, LogThing3, $
		FILENAME=FileName, YESLOG=YesLog, NOLOG=NoLog
;+
; NAME: CISSCAL_Log
;
; PURPOSE: 'Log to file' utility for IDL Cassini Image Calibration suite
;		Provides redirectable information/error logging.
;
; MAJOR TOPICS: CISSCAL
;
; CALLING SEQUENCE: CISSCAL_Log, LogThing0, LogThing1, LogThing2, LogThing3, $
;		FILENAME=FileName, YESLOG=YesLog, NOLOG=NoLog
;
; OPTIONAL INPUT PARAMETERSS:
;     LogThing0..3:	Information to log (eventually via a PRINTF statement)
;
; KEYWORD PARAMETERS:
;     FILENAME:		Name of a file to which to send log messages until
;			 further notice. The strings 'stdout' and 'stderr' are
;			 also recognised and handled appropriately.
;			 The string 'gui' is also recognised, and causes output
;			 to be delegated to the procedure GuiPrint.
;     NOLOG:		Switches logging OFF until further notice
;     YESLOG:		Switches logging ON until further notice (overrides NOLOG)
;			 overwriting it: otherwise this keyword is ignored
; COMMON BLOCKS and STRUCTURES:
;     LogCommon (for internal persistence only).
;
; SIDE EFFECTS:
;     None.
;
; MODIFICATION HISTORY:  Initial coding: Kevin Beurle, November 2000
;                        Modifications: 
;                         Implemented Shawn Ewald's suggestions
;                         Changed "LOGYES" to "YESLOG"
;                         Cleaned up syntax
;                         Changed code so that, if logging to a file,
;                          file is opened and closed on each write, and
;                          messages are always appended.
;                                  - Ben Knowles, Nov. 19, 2004
;-

;	Just to preserve LogLun, LogOn, LogFile between invocations 
;       (c.f. 'static' in C):
COMMON LogCommon, LogLun, LogOn, LogFile

;	LogLun is the LUN that we are currently sending logging information
;	 to: a value of zero means we are sending it to the GuiPrint procedure.
;	LogOn is the current logging status: log nothing if this is zero

;	Has LogLun been defined yet? Default to logging to GUI (0) if not.
LogInfo = SIZE(LogLun)
IF ( LogInfo[LogInfo[0]+1] EQ 0 ) THEN BEGIN
  LogLun = 0
  LogOn = 1
ENDIF

;	Handle logging ON and OFF switches: ON takes precedence
IF KEYWORD_SET(NoLog) THEN LogOn = 0
IF KEYWORD_SET(YesLog) THEN LogOn = 1

;	If a filename is given then close the current
;		logfile and direct logging to the named one:
;	Close the current LUN unless it's stdout (-1) or stderr (-2)
IF KEYWORD_SET(FileName) THEN BEGIN

  IF (LogLun GT 0 ) THEN FREE_LUN, LogLun

;	Now open the new log stream:
;	 just set LogLun appropriately if the name is 'stdin' or 'stderr'
;	 otherwise open the named file for output
;	Presume that logging should be switched ON unless explicitly denied
  IF STRLOWCASE(FileName) EQ 'stdout' THEN BEGIN
    LogLun = -1
  ENDIF ELSE IF STRLOWCASE(FileName) EQ 'stderr' THEN BEGIN
    LogLun = -2
  ENDIF ELSE IF STRLOWCASE(FileName) EQ 'gui' THEN BEGIN
    LogLun = 0
  ENDIF ELSE BEGIN
    LogFile = FileName
    LogLun = 1
  ENDELSE
  IF NOT KEYWORD_SET(NoLog) THEN LogOn = 1
ENDIF

;	If logging is switched on we can now do the actual output
IF LogOn THEN BEGIN
;	On some versions and platforms an empty LogThing0
;	 was triggering an 'undefined' error: fix this if so
  LTSize = SIZE(LogThing0)
  IF LTSize[LTSize[0]+1] EQ 0 THEN LogThing0 = '<Undefined message fix>'

;       This is to fix the problem of fstat being a structure in newer
;        versions of IDL:
  LTSize = size(LogThing1)
  IF LTSize[LTSize[0]+1] eq 8 THEN LogThing0 = '<Struct message fix>'

; The code below was cleaned up with Shawn Ewald's suggestions:

  nargs = N_PARAMS()
  IF nargs LT 4 THEN LogThing3 = ''
  IF nargs LT 3 THEN LogThing2 = ''
  IF nargs LT 2 THEN LogThing1 = ''
  IF nargs LT 1 THEN LogThing0 = ''

  IF LogLun NE 0 THEN BEGIN
      IF LogLun GT 0 THEN OPENW, LogLun, LogFile, /GET_LUN, /APPEND
      PRINTF, LogLun, LogThing0, LogThing1, LogThing2, LogThing3
      IF LogLun GT 0 THEN FREE_LUN, LogLun
  ENDIF ELSE BEGIN
      GuiString = STRING(LogThing0) + ' ' + STRING(LogThing1) $
                  + ' ' + STRING(LogThing2) + ' ' + STRING(LogThing3)
      GuiPrint, GuiString
  ENDELSE
ENDIF

END
