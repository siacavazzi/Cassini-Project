;;	cisscal_gui.pro
;;	Graphical User Interface for IDL Cassini Image Calibration suite
;;
;;	Kevin Beurle	16th Sept 1998 to 18th December 1998
;;		        Revised July 1999
;;
;;      Version 2.0 release by Ben Knowles (2004/05/17)
;;
;;      Subsequent releases by Ben Knowles through Version 3.9 (2018/08/06)
;;
;;	Start with a number of "utility" procedures...
;;

;;	FUNCTION Defined
;;	Return TRUE if its argument is defined
FUNCTION Defined, Arg
  SzArg = SIZE(Arg)
  RETURN, (SzArg[SzArg[0]+1] NE 0)
END
;;
;;	PRO GuiPrint
;;	 Little utility procedure to simulate PRINT behaviour to text widget
;	Ideally use somehing like this eventually to "swallow" all
;	the text logging output (i.e. PRINT lines) into the GUI logging window
PRO GuiPrint, Arg1, Arg2, Arg3, Arg4, Arg5
@cisscal_common.pro	; include COMMON definitions

  IF Defined(Arg1) THEN WIDGET_CONTROL, GuiText, /APPEND, SET_VALUE=STRING(Arg1)
  IF Defined(Arg2) THEN WIDGET_CONTROL, GuiText, /APPEND, SET_VALUE=STRING(Arg2)
  IF Defined(Arg3) THEN WIDGET_CONTROL, GuiText, /APPEND, SET_VALUE=STRING(Arg3)
  IF Defined(Arg4) THEN WIDGET_CONTROL, GuiText, /APPEND, SET_VALUE=STRING(Arg4)
  IF Defined(Arg5) THEN WIDGET_CONTROL, GuiText, /APPEND, SET_VALUE=STRING(Arg5)

END

;;	FUNCTION ToStr
;;	 Little utility to format things as strings more cleanly
FUNCTION ToStr, Arg

  IF N_PARAMS() NE 1 THEN RETURN, ''

  ArgSize = SIZE(Arg)
  CASE ArgSize[0] OF
    0: Result = STRTRIM(STRING(Arg),2)
    1: BEGIN
      Result = '[ '
      FOR K = 1, ArgSize[1]-1 DO BEGIN
        Result = Result + STRTRIM(STRING(Arg[K-1]),2) + ', '
      ENDFOR
      Result = Result + STRTRIM(STRING(Arg[ArgSize[1]-1]),2) + ' ]'
      END
    ELSE: Result = '[Array of dimension ' + STRTRIM(STRING(ArgSize[0]),2) + ']'
  ENDCASE
  RETURN, Result
END

;;	PRO GuiEnabMenuOpts
;;	 Enable (or disable) the GUI menu options that are only
;;	  valid when an image has been loaded
PRO GuiEnabMenuOpts, ImageIsLoaded
@cisscal_common.pro	; include COMMON definitions

;	Default w/o argument is to enable the appropriate menu options..
;	if we do have an argument then use that to choose
  IF N_PARAMS() EQ 0 THEN ImageIsLoaded=1

  FOR I = 1, N_ELEMENTS(GreyableButtons) DO BEGIN
    WIDGET_CONTROL, GreyableButtons[I-1], SENSITIVE=ImageIsLoaded
  ENDFOR
END

;;	PRO GuiTrackCursor
;;	 Use cursor in image window to select pixel coordinates
PRO GuiTrackCursor, ImageObj, Coords
@cisscal_common.pro	; include COMMON definitions

  GuiPrint,''
  IF NOT OBJ_VALID(ImageObj) THEN BEGIN
	GuiPrint, 'No image loaded!'
	RETURN
  ENDIF

  GuiPrint,'** Click in image window to select {line, sample} to profile **'

  WSET, ImageWindow
  WSHOW

  CursX = Coords[0]
  CursY = Coords[1]
  TVCRS, CursX, CursY, /NORMAL
  CURSOR, CursX, CursY, /NORMAL
; PRINT,'Selected: ', CursX, CursY	; note: normalised 0..1 coords at this point
  Coords = [ CursX, CursY ]
END

;;	PRO GuiMakeWin
;;	 Make a new graphics window
PRO GuiMakeWin, Window, ImgObj
@cisscal_common.pro	; include COMMON definitions
  CASE Window OF
    ImageWindow:	Title=['Image', 'PrintImg']
    HistWindow:	        Title=['Pixel value histogram', 'PrintHisto']
    ProfWindow:	        Title=['Pixel value profiles', 'PrintProfile']
    ProfAveWindow:	Title=['Averaged pixel value profiles', $
				'PrintProfAve']
    GraphWindow:	Title=['General graphics', 'PrintNoGraph']
    OverclkWindow:      Title=['Overclocked pixels', 'PrintOverclocks']
  ELSE:	Title=['Window ' + STRING(Window), 'PrintNoGraph']
  ENDCASE

;  print,'make window [' + Title[0] + ', ' + Title[1] + ']'
  BaseW = WIDGET_BASE(GROUP_LEADER=GuiBase,TITLE=Title[0], $
		/COLUMN,/BASE_ALIGN_CENTER)
  IF Window eq OverclkWindow then DrawW = WIDGET_DRAW(BaseW, XSIZE=1024, YSIZE=512) else $
      DrawW = WIDGET_DRAW(BaseW, XSIZE=640, YSIZE=512)
  ButtonW = WIDGET_BASE(BaseW, /ROW)
  PrintW = WIDGET_BUTTON(ButtonW, VALUE='Print', UVALUE=Title[1])
  DoneW = WIDGET_BUTTON(ButtonW, VALUE='Dismiss', UVALUE='WinDone')

;	Stash a reference to the image object into the base widget's UVALUE
  WIDGET_CONTROL, BaseW, SET_UVALUE=ImgObj

  WIDGET_CONTROL, BaseW, /REALIZE
  WIDGET_CONTROL, DrawW, GET_VALUE=WinId
  XMANAGER, 'GraphWin', BaseW, /NO_BLOCK
  GuiWinBase[Window] = BaseW
  GuiWinDraw[Window] = DrawW
  GuiWinPrint[Window] = PrintW
  GuiWinId[Window] = WinId
END

;;	PRO GuiSelectWin
;;	 Select a graphics window, opening it with appropriate title
;;	  if it doesn't already exist
PRO GuiSelectWin, Window, ImgObj
@cisscal_common.pro	; include COMMON definitions
;  print,'select window',window

  WinIdSize = SIZE(GuiWinId)
  IF (Window LT 0) OR (Window GE WinIdSize[1]) THEN BEGIN
     Print,''
     Print,'Invalid window requested:',Window
     RETURN
  ENDIF

  IF GuiWinId[Window] EQ -1 THEN GuiMakeWin, Window, ImgObj

  ExceptionCount = 0
  CATCH, Exception
  IF Exception NE 0 THEN BEGIN
    ExceptionCount = ExceptionCount+1
    IF ExceptionCount GT 4 THEN BEGIN
      PRINT,'Multiple exceptions noted'
      RETURN
    ENDIF
    CASE Exception OF
      -386 : PRINT, 'Reopening required window'
      -524 : PRINT, 'Reopening required window' ;? at least this is cleaner
      -525 : PRINT, 'Reopening required window' ;? at least this is cleaner
      -529 : PRINT, 'Reopening required window' ;? at least this is cleaner
      -531 : PRINT, 'Reopening required window' ;? at least this is cleaner
      ELSE : BEGIN
        HELP,CALLS=A
        PRINT,'Handling exception ' + STRING(Exception) $
			+ ' (' + !ERR_STRING + ')'
        PRINT,' at ' + A[0] + ' from ' + A[1]
      END
    ENDCASE
    GuiMakeWin, Window, ImgObj
  ENDIF

  WSET, GuiWinId[Window]
  WSHOW
END

;;
;;	Procedures/functions which implement the menu commands...
;;
;;	FUNCTION GuiOpenFile
;;	 Have a filename selected and attempt to open
;;	  this file as an image
FUNCTION GuiOpenFile, ImageObj, FileName = FileName
@cisscal_common.pro	; include COMMON definitions

  ImPathSz = SIZE(ImPath)
  IF ( ImPathSz[ImPathSz[0]+1] NE 7 ) THEN BEGIN	; if not a string
      ImPath = ImageBaseDir
  ENDIF

  GuiPrint, ''
  GuiPrint, 'Opening image file...'

  save_impath = ImPath

  IF NOT keyword_set(FileName) THEN FileName = DIALOG_PICKFILE(/READ, FILTER='*', $
	TITLE='Select Image file', PATH=ImPath, GET_PATH=ImPath)

;       Throw out old ImageObj if we've already used it
  IF OBJ_VALID(ImageObj) THEN OBJ_DESTROY,ImageObj

;	Return null object if the filename is blank
  ImageObj = OBJ_NEW()

  IF FileName EQ '' THEN BEGIN  ; remember path if no file selected
      ImPath = save_impath      ; (added by Shawn Ewald)
      RETURN,ImageObj
  ENDIF

;; spe caltech 2005 april
;; if the file does not exist, do not try to open it.
;; go wait for the next command.
  IF (NOT FILE_TEST(FileName)) THEN BEGIN
      ImPath = save_impath
      RETURN, ImageObj
  ENDIF

;; spe caltech 2005 april - it makes no sense to ask cisscal to open
;; a directory.  assume it was a typo and go wait for next command.
  IF (FILE_TEST(FileName, /DIRE)) THEN BEGIN
      ImPath = save_impath
      RETURN, ImageObj
  ENDIF

; set output path to selected directory:
  OutImPath = ImPath

  ImageObj = OBJ_NEW('CassImg') 
  WIDGET_CONTROL, /HOURGLASS
  ImageObj->ReadVic, FileName,/Quiet

; make sure image is valid Cassini ISS image:
  IF long(ImageObj->Name()) gt 0L then begin
     GuiPrint, 'Image ' + FileName + ' loaded!'
     GuiImageName = FileName
  ENDIF ELSE BEGIN
     ImageObj = OBJ_NEW()
  ENDELSE

  GuiShowLabel, ImageObj

  RETURN, ImageObj
END

;;	PRO GuiShowLabel
;;	List VICAR labels in the labels window
;          Note: used to be GuiTabulateLabels, BDK 10/25/2012
PRO GuiShowLabel, ImageObj
@cisscal_common.pro	; include COMMON definitions

  IF GuiTableBase NE -1 THEN BEGIN
     WIDGET_CONTROL, GuiTableBase, /DESTROY ; Get rid of old labels
     GuiTableBase = -1
  ENDIF

  IF OBJ_VALID(ImageObj) AND ShowLabelYes THEN BEGIN

     LabelArray = ImageObj->LabelArray()
     MyLabel = 'VICAR label for image: ' + STRTRIM(ImageObj->Name(),2)

     GuiTableBase = WIDGET_BASE(GuiUpperBase,/COLUMN,xpad=0,ypad=0)
     GuiTableLbl = WIDGET_LABEL(GuiTableBase, VALUE=MyLabel)
     GuiTable = WIDGET_TABLE(GuiTableBase, VALUE=LabelArray[1,*], $
                             COLUMN_LABELS=['Value'], $
                             ROW_LABELS=LabelArray[0,*], $
                             COLUMN_WIDTHS=10, UNITS=2, SCR_XSIZE=12,SCR_YSIZE=17,$
                             /RESIZEABLE_COLUMNS, /SCROLL)
  ENDIF

END

;;	PRO GuiSaveFile
;;	 Will write out a processed file
PRO GuiSaveFile, ImgObj, FileName=FileName
@cisscal_common.pro

  GuiPrint,''
  GuiPrint, 'Saving image file...'

  IF NOT OBJ_VALID(ImgObj) THEN BEGIN
     GuiPrint, '  No image loaded!'
     RETURN
  ENDIF

  OutImPathSz = SIZE(OutImPath)
  IF ( OutImPathSz[OutImPathSz[0]+1] NE 7 ) THEN BEGIN ; if not a string
      OutImPath = ImageBaseDir
  ENDIF

  IF NOT keyword_set(FileName) then begin
      GuiCalImageName = strmid(GuiImageName,0,strpos(GuiImageName,'.',/reverse_search))+$
                        (*BatchParams).outputext
      SaveFName = DIALOG_PICKFILE(/WRITE, FILTER='*'+(*BatchParams).outputext, FILE=GuiCalImageName, $
                                  PATH=OutImPath, GET_PATH=OutImPath)
  ENDIF ELSE BEGIN
      SaveFName = FileName
  ENDELSE

  ImgObj->WriteVic,SaveFName
;  GuiShowLabel, ImgObj	; update labels window (LBLSIZE may have changed...)
END

;;	PRO GuiSatFile
;;	Write file of saturated pixels
PRO GuiSatFile, ImgObj
@cisscal_common.pro	; include COMMON definitions

  GuiPrint, ''
  GuiPrint, 'Save saturated pixels file...'

  IF NOT OBJ_VALID(ImgObj) THEN BEGIN
     GuiPrint, '  No image loaded!'
     RETURN
  ENDIF

  OutImPathSz = SIZE(OutImPath)
  IF ( OutImPathSz[OutImPathSz[0]+1] NE 7 ) THEN BEGIN	; if not a string
    OutImPath = '.'
  ENDIF

  SatFName = DIALOG_PICKFILE(/WRITE, FILE=GuiImageName + '.sat', $
	FILTER='*.sat', PATH=OutImPath, GET_PATH=OutImPath)
;  OPENW, SatFLun, SatFName, /GET_LUN

; This was changed so that CISSCAL now writes an actual VICAR file:
;  Sat_Pixels = ImgObj->Saturated()
;  PRINTF, SatFLun, Sat_Pixels
;  CLOSE, SatFLun
;  FREE_LUN, SatFLun

  ImgObj->WriteVic,SatFName,imagetype='saturated'

END

;;	PRO GuiMissFile
;;	Write file of missing pixels
PRO GuiMissFile, ImgObj
@cisscal_common.pro	; include COMMON definitions

  GuiPrint, ''
  GuiPrint, 'Save missing pixels file...'

  IF NOT OBJ_VALID(ImgObj) THEN BEGIN
     GuiPrint, '  No image loaded!'
     RETURN
  ENDIF

  OutImPathSz = SIZE(OutImPath)
  IF ( OutImPathSz[OutImPathSz[0]+1] NE 7 ) THEN BEGIN	; if not a string
    OutImPath = '.'
  ENDIF

  MissFName = DIALOG_PICKFILE(/WRITE, FILE=GuiImageName + '.miss', $
	FILTER='*.miss', PATH=OutImPath, GET_PATH=OutImPath)

; This was changed so that CISSCAL now writes an actual VICAR file:
;  OPENW, MissFLun, MissFName, /GET_LUN
;  Miss_Pixels = ImgObj->Missing()
;  PRINTF, MissFLun, Miss_Pixels
;  CLOSE, MissFLun
;  FREE_LUN, MissFLun

  ImgObj->WriteVic,MissFName,imagetype='missing'

END


;;      PRO GuiMaskFile
;;      Write dark-sky mask file
PRO GuiMaskFile, ImgObj
@cisscal_common.pro     ; include COMMON definitions

  GuiPrint, ''
  GuiPrint, 'Save mask file...'

  IF NOT OBJ_VALID(ImgObj) THEN BEGIN
     GuiPrint, '  No image loaded!'
     RETURN
  ENDIF

  OutImPathSz = SIZE(OutImPath)
  IF ( OutImPathSz[OutImPathSz[0]+1] NE 7 ) THEN BEGIN	; if not a string
    OutImPath = '.'
  ENDIF

  MaskFName = DIALOG_PICKFILE(/WRITE, FILE=GuiImageName + '.mask', $
	FILTER='*.mask', PATH=OutImPath, GET_PATH=OutImPath)

; This was changed so that CISSCAL now writes an actual VICAR file:
;  OPENW, MaskFLun, MaskFName, /GET_LUN
;  Mask_Pixels = ImgObj->Mask()     ; NO FUNCTION CURRENTLY DEFINED
;  PRINTF, MaskFLun, Mask_Pixels
;  CLOSE, MaskFLun
;  FREE_LUN, MaskFLun

  ImgObj->WriteVic,MaskFName,imagetype='mask'

END

;*****************************

;;	PRO GuiImgDisp
;;	 Display the image in a graphics window
;;	 Various keyword parameters allow a choice of image scaling law
;;	 Window is image-sized, or 512*512 if that is smaller
;;	  (call with *one* scaling keyword only, or behaviour is undefined)
PRO GuiImgDisp, ImageObj, HistEq=HistEq, Sqrt=Sqrt, Log=Log, Stretch=Stretch, Slider=Slider, Mask=Mask
@cisscal_common.pro	; include COMMON definitions

  GuiPrint, ''   
  IF NOT OBJ_VALID(ImageObj) THEN BEGIN
     GuiPrint, 'No image loaded!'
     RETURN
  ENDIF

  WIDGET_CONTROL, /HOURGLASS
  IF KEYWORD_SET(HistEq) THEN BEGIN
    ScalTyp = 'histogram-equalized'
    TvImg = HIST_EQUAL(ImageObj->Image())
  ENDIF ELSE IF KEYWORD_SET(Stretch) THEN BEGIN
    ScalTyp = 'stretched'
;   Stretch from 0.2% to 99.8% centiles of pixel values into full display range
    TvImg = ImageObj->Image()
    Orderlist = SORT(TvImg)
    LowIndex = N_ELEMENTS(Orderlist) / 500
    LowPixVal = TvImg[Orderlist[LowIndex]]
    HighIndex = N_ELEMENTS(Orderlist) - LowIndex
    HighPixVal = TvImg[Orderlist[HighIndex]]
;    GuiPrint,'Length and indices:', N_ELEMENTS(Orderlist), LowIndex, HighIndex
;    GuiPrint,'Stretch endpoints:', OrderList[LowIndex], OrderList[HighIndex]
;    GuiPrint,'Stretch end values:', TvImg[OrderList[LowIndex]], TvImg[OrderList[HighIndex]]
    TvImg = (ImageObj->Image() > LowPixVal) < HighPixVal
    TvImg = (TvImg - MIN(TvImg))*256/(MAX(TvImg)-MIN(TvImg))
  ENDIF ELSE IF KEYWORD_SET(Log) THEN BEGIN
    ScalTyp = 'log scaled'
    TvImg = ALOG(ImageObj->Image() > 1E-20)
  ENDIF ELSE IF KEYWORD_SET(Sqrt) THEN BEGIN
    ScalTyp = 'square root scaled'
    TvImg = SQRT(ImageObj->Image() > 0)
  ENDIF ELSE IF KEYWORD_SET(Mask) THEN BEGIN
    ScalTyp = 'mask'
    TvImg = mask < 0.5
  ENDIF ELSE BEGIN
    ScalTyp = 'linearly scaled'
    TvImg = ImageObj->Image()
  ENDELSE

  ImSize = SIZE(TvImg)
  DispXsize = ImSize[1] < 512	; Lesser of (512, Image Xsize)
  DispYsize = ImSize[2] < 512	; Lesser of (512, Image Ysize)

  TvImg = reverse(TvImg,2)  ; because image orientation in IDL flipped about x axis

  GuiPrint, 'Display ' + ScalTyp + ' image...'
  WinTitle = 'Image ' + ImageObj->Name() + ' (' + ScalTyp + ')'

  IF ScalTyp NE 'mask' THEN $
     GuiPrint, '  Image min  : '+string(min(ImageObj->Image()))+$
               '  Image max  : '+string(max(ImageObj->Image()))

  IF ScalTyp EQ 'stretched' THEN $
     GuiPrint, '  Display min: '+string(LowPixVal)+$
               '  Display max: '+string(HighPixVal)

  IF NOT KEYWORD_SET(Slider) THEN BEGIN
    WINDOW, ImageWindow, TITLE=WinTitle, XSIZE=DispXsize, YSIZE=DispYsize
    if ImSize[1] eq 1024 then TvImg = rebin(TvImg, 512, 512)
    TVSCL, TvImg
    ImageWinValid = 1
  ENDIF ELSE BEGIN
;    GuiPrint, 'Display in sliding window pair...'
    TvImg = BYTSCL(TvImg)
    SLIDE_IMAGE, TvImg, GROUP=GuiBase, TITLE=WinTitle
  ENDELSE
END



;;	PRO GuiToolsHisto
;;	 Plot a histogram of pixel value frequency
PRO GuiToolsHisto, ImageObj, Print=Print, Log=Log
@cisscal_common.pro	; include COMMON definitions

  GuiPrint,''
  IF NOT OBJ_VALID(ImageObj) THEN BEGIN
     GuiPrint, 'No image loaded!'
     RETURN
  ENDIF

  MyImgCopy = ImageObj->Image()

  HistoLow = MIN(MyImgCopy) < 0
  PixHisto = HISTOGRAM(MyImgCopy,MIN=HistoLow)
  HistoSize = SIZE(PixHisto)
  HistoLength = HistoSize[1]
  PlotTitle = 'Pixel value histogram, Image ' + ImageObj->Name()
  IF KEYWORD_SET(Print) THEN BEGIN
     SET_PLOT,'ps'
     PrintFile = STRTRIM(ImageObj->Name(),2) + '_hist.ps'
     DEVICE,FILENAME=PrintFile, /LANDSCAPE
     GuiPrint,'Printing image histogram as ' + Printfile
  ENDIF ELSE BEGIN
     SET_PLOT,'x'
     GuiSelectWin, HistWindow, ImageObj
  ENDELSE
  !P.MULTI = [ 0, 1, 1]         ; Single plot on page
  PixValues = INDGEN(HistoLength)+HistoLow
; print,'pixvalues runs from', PixValues[0], ' to', PixValues[HistoLength-1]
  IF KEYWORD_SET(Log) THEN MyMinVal = 1 ELSE MyMinVal=0
  PLOT, PixValues, PixHisto, TITLE=PlotTitle, YLOG=Log, MIN_VALUE=MyMinVal, $
        XTITLE='Pixel Value', YTITLE='Number of pixels', PSYM=10
  
  IF KEYWORD_SET(Print) THEN DEVICE,/CLOSE

END


;;	PRO GuiToolsProf
;;	 Plot profiles of pixel values along a line and a sample column
;;	 These can be selected by cursor if an image is displayed,
;;	  otherwise defaults to the centre of the image
PRO GuiToolsProf, ImageObj, Print=Print
@cisscal_common.pro	; include COMMON definitions
COMMON	ProfilePersist, CoordPair, Vector1, Vector2

  GuiPrint, ''
  IF NOT OBJ_VALID(ImageObj) THEN BEGIN
     GuiPrint, 'No image loaded!'
     RETURN
  ENDIF

  IF NOT KEYWORD_SET(Print) THEN BEGIN
    Image = ImageObj->Image()
    ImSize = SIZE(Image)
    ImRect = [ ImSize[1], ImSize[2] ]	; i.e. [ xsize, ysize ]

;	Default to centre line and sample column
    ProfCoord = [0.5, 0.5]

 ; display image in image window
    ScalTyp = 'linearly scaled'
    DispXsize = ImSize[1] < 512	; Lesser of (512, Image Xsize)
    DispYsize = ImSize[2] < 512	; Lesser of (512, Image Ysize)
;  GuiPrint, 'Display ' + ScalTyp + ' image...'
    WinTitle = 'Image ' + ImageObj->Name() + ' (' + ScalTyp + ')'
    WINDOW, ImageWindow, TITLE=WinTitle, XSIZE=DispXsize, YSIZE=DispYsize
    if ImSize[1] eq 1024 then TvImg = rebin(Image, 512, 512) else $
      TvImg = Image
    TVSCL, TvImg       ;displayed image will appear "flipped"; leave as-is for now
    ImageWinValid = 1

;	Activate image cursor to allow [line,sample] selection
    GuiTrackCursor, ImageObj, ProfCoord

    CoordPair = FIX(ImRect * ProfCoord)
    Vector1 = Image[CoordPair[0],*]
    Vector2 = Image[*,CoordPair[1]]

    GuiPrint,'Selected: ' + ToStr(CoordPair)
    SET_PLOT,'x'
    GuiSelectWin, ProfWindow, ImageObj
  ENDIF ELSE BEGIN
    SET_PLOT,'ps'
    PrintFile = STRTRIM(ImageObj->Name(),2) + '_prof.ps'
    DEVICE,FILENAME=PrintFile, /LANDSCAPE
    GuiPrint,'Printing profiles graph as ' + Printfile
  ENDELSE

  PlotTitle = 'Line and sample pixel value profiles, Image ' + ImageObj->Name()
  YTitle1 = 'Pixel values, sample ' + STRTRIM(STRING(CoordPair[0]),2)
  YTitle2 = 'Pixel values, line ' + STRTRIM(STRING(CoordPair[1]),2)
  !P.MULTI = [ 0, 1, 2]		; Stack two plots vertically
  PLOT, Vector1, YTITLE=YTitle1, XTITLE='Line', $
	XSTYLE=3, TICKLEN=-0.02, TITLE = PlotTitle, /ynozero
  PLOT, Vector2, YTITLE=YTitle2, XTITLE='Sample', $
	XSTYLE=3, TICKLEN=-0.02, /ynozero

  IF KEYWORD_SET(Print) THEN DEVICE,/CLOSE
  SET_PLOT,'x'
END


;;	PRO GuiToolsProfAve
;;	 Plot profiles of line and sample averaged pixel values
PRO GuiToolsProfAve, ImageObj, Print=Print
@cisscal_common.pro	; include COMMON definitions

  GuiPrint, ''
  IF NOT OBJ_VALID(ImageObj) THEN BEGIN
     GuiPrint, 'No image loaded!'
     RETURN
  ENDIF

  Image = ImageObj->Image()
  ImSize = SIZE(Image)
  ImRect = [ ImSize[1], ImSize[2] ]	; i.e. [ xsize, ysize ]

;	Form the two marginal sums and scale to means
  Marg1 = TOTAL(Image, 1) / ImRect[0]
  Marg2 = TOTAL(Image, 2) / ImRect[1]
  IF KEYWORD_SET(Print) THEN BEGIN
    SET_PLOT,'ps'
    PrintFile = STRTRIM(ImageObj->Name(),2) + '_ave.ps'
    DEVICE,FILENAME=PrintFile, /LANDSCAPE
    GuiPrint,'Printing average profiles graph as ' + Printfile
  ENDIF ELSE BEGIN
    SET_PLOT,'x'
    GuiSelectWin, ProfAveWindow, ImageObj
  ENDELSE

  PlotTitle = 'Average pixel value profiles, Image ' + ImageObj->Name()
  !P.MULTI = [ 0, 1, 2]		; Stack two plots vertically
  PLOT, Marg1, YTITLE='Mean pixel value', XTITLE='Line', $
	XSTYLE=3, TICKLEN=-0.02, TITLE = PlotTitle, /ynozero
  PLOT, Marg2, YTITLE='Mean pixel value', XTITLE='Sample', $
	XSTYLE=3, TICKLEN=-0.02, /ynozero

  IF KEYWORD_SET(Print) THEN DEVICE,/CLOSE
END

;;	PRO GuiToolsInspect
;;	 Inspect pixel values in image
PRO GuiToolsInspect, ImageObj
@cisscal_common.pro	; include COMMON definitions

  GuiPrint, ''
  IF NOT OBJ_VALID(ImageObj) THEN BEGIN
     GuiPrint, 'No image loaded!'
     RETURN
  ENDIF

  GuiPrint, 'Inspect screen pixel values (note: image size may be scaled)...'
  GuiPrint, '** Left-click to see sample, line values; right-click to finish **'

 ; display image in image window
  ScalTyp = 'linearly scaled'
  Image = ImageObj->Image()

  ImSize = SIZE(Image)
  DispXsize = ImSize[1] < 512	; Lesser of (512, Image Xsize)
  DispYsize = ImSize[2] < 512	; Lesser of (512, Image Ysize)

;  GuiPrint, 'Display ' + ScalTyp + ' image...'
  WinTitle = 'Image ' + ImageObj->Name() + ' (' + ScalTyp + ')'
  WINDOW, ImageWindow, TITLE=WinTitle, XSIZE=DispXsize, YSIZE=DispYsize
  if ImSize[1] eq 1024 then begin
      TvImg = rebin(Image, 512, 512)
      sizescl = 2.0
  endif else begin
      TvImg = Image
      sizescl = 1.0
  endelse
  TVSCL, reverse(TvImg,2)
  ImageWinValid = 1

  Cisscal_Rdpix, reverse(TvImg,2), scale=sizescl
END

;;	PRO GuiPlotOverclocks
;;	 Plot profiles of line and sample averaged pixel values
PRO GuiPlotOverclocks, ImageObj, Print=Print
@cisscal_common.pro	; include COMMON definitions

  overclocks = ImageObj->OverclockAvg()

;	Form the two marginal sums and scale to means
  IF KEYWORD_SET(Print) THEN BEGIN
    SET_PLOT,'ps'
    PrintFile = STRTRIM(ImageObj->Name(),2) + '_overclk.ps'
    DEVICE,FILENAME=PrintFile, /LANDSCAPE
    GuiPrint,'Printing overclocks graph as ' + Printfile
  ENDIF ELSE BEGIN
    SET_PLOT,'x'
    GuiSelectWin, OverclkWindow, ImageObj
  ENDELSE

  PlotTitle = 'Line-averaged overclocked pixels, Image ' + ImageObj->Name()
  !P.MULTI = [ 0, 1, 1]		; Single plot on page
  PLOT, overclocks, YTITLE='Mean overclocked pixel value', XTITLE='Line', $
        XSTYLE=3, TICKLEN=-0.02, TITLE = PlotTitle, /ynozero, $
        YRANGE=[min(overclocks)-1,max(overclocks+1)]

  IF KEYWORD_SET(Print) THEN DEVICE,/CLOSE
END

;;	PRO GuiHelpAbout
;;	 Display attribution information
PRO GuiHelpAbout
@cisscal_common.pro
  MsgText = [ 'CISSCAL '+CisscalVers, 'Cassini Radiometric Calibration Suite', $
        'Theoretical basis and pipeline by Robert A. West',$
        'Jet Propulsion Laboratory',$
        'Pasadena, California, USA',$
        '<Robert.A.West@jpl.nasa.gov>',$
	'Initial systems design and implementation by Kevin Beurle', $
	'Astronomy Unit, Mathematical Sciences', $
	'Queen Mary & Westfield College, London', $
	'<K.Beurle@qmw.ac.uk>',$
        'Re-design, updates, additions and final implementation by Ben Knowles',$
        'Cassini Imaging Central Laboratory for Operations (CICLOPS)',$
        'Space Science Institute', $
        'Boulder, Colorado, USA', $
        '<ben.cisscal@gmail.com>']
  Result = DIALOG_MESSAGE(MsgText, /INFORMATION, TITLE='Help about')
END

;;	PRO GuiQuit
;;	 Shut down the GUI and all graphics windows
PRO GuiQuit, ev
@cisscal_common.pro	; include COMMON definitions

  ExceptionCount = 0
  CATCH, Exception

  IF Exception NE 0 THEN BEGIN
    ExceptionCount = ExceptionCount+1
    IF ExceptionCount GT 2 THEN BEGIN
      PRINT,'Multiple exceptions noted'
      RETURN
    ENDIF
    CASE Exception OF
      -383 : PRINT, 'No window to be closed'
      -488 : PRINT, 'Unexpected widget (' + !ERR_STRING + ')'

      ELSE : BEGIN
          PRINT, 'GuiQuit received exception ' + STRING(Exception) $
		+ ' (' + !ERR_STRING + ')'
          END
    ENDCASE
  ENDIF

; free pointers to avoid memory leaks (B. Knowles, 12/19/03):

  if ptr_valid(CalOptions) then begin
      if ptr_valid((*CalOptions).lutc) then begin
          ptr_free,(*CalOptions).lutc
      endif
      if ptr_valid((*CalOptions).bitw) then begin
          ptr_free,(*CalOptions).bitw
      endif
      if ptr_valid((*CalOptions).bias) then begin          
          ptr_free,(*CalOptions).bias
      endif
      if ptr_valid((*CalOptions).twohz) then begin
          if ptr_valid((*(*CalOptions).twohz).imagemean) then begin
              ptr_free,(*(*CalOptions).twohz).imagemean
          endif 
          ptr_free,(*CalOptions).twohz
      endif
      if ptr_valid((*CalOptions).dark) then begin
          ptr_free,(*CalOptions).dark
      endif
      if ptr_valid((*CalOptions).abpp) then begin
          ptr_free,(*CalOptions).abpp
      endif
      if ptr_valid((*CalOptions).lin) then begin
          ptr_free,(*CalOptions).lin
      endif
      if ptr_valid((*CalOptions).flat) then begin
          ptr_free,(*CalOptions).flat
      endif
      if ptr_valid((*CalOptions).flux) then begin
          if ptr_valid((*(*CalOptions).flux).ioverf) then begin
              ptr_free,(*(*CalOptions).flux).ioverf
          endif
          ptr_free,(*CalOptions).flux
      endif
      if ptr_valid((*CalOptions).corr) then begin
          ptr_free,(*CalOptions).corr
      endif
      if ptr_valid((*CalOptions).geom) then begin
          ptr_free,(*CalOptions).geom
      endif
      
      ptr_free,CalOptions
  endif

  if ptr_valid(BatchParams) then begin
      if ptr_valid((*BatchParams).dark) then begin
          if ptr_valid((*(*BatchParams).dark).names) then begin
              ptr_free,(*(*BatchParams).dark).names
          endif
          ptr_free,(*BatchParams).dark
      endif

      ptr_free,BatchParams
  endif

;	Close down the GUI
  PRINT, 'Shutting down the GUI...'
  WIDGET_CONTROL, ev.top, /DESTROY

;	and shut any windows we opened
  PRINT, 'closing non-widget graphics windows...'
;  WDELETE, ImageWindow, HistWindow, ProfWindow, ProfAveWindow, $
;    GraphWindow, OverclkWindow

; Shutdown exception fixed by Shawn Ewald by adding IF statement:
  IF (ImageWindow NE 0) THEN WDELETE, ImageWindow

  PRINT, 'Finished.'
END


;;	PRO GuiImgCal
;;	Run image through the radiometric calibration steps
;
;	Altered 4/02 by Ben Knowles to send selected dark image to
;		dark subtraction routine
;       Altered 12/03 by Ben Knowles to accomodate new radiomcalib
;               routine and changes to the GUI
PRO GuiImgCal, ImgObj
@cisscal_common.pro	; include COMMON definitions

  IF NOT OBJ_VALID(ImgObj) THEN BEGIN
     GuiPrint, ''
     GuiPrint, 'No image loaded!'
     RETURN
  ENDIF

  WIDGET_CONTROL, /HOURGLASS
  ImgObj->RadiomCalib, CancelFlag=CancelFlag

  IF CancelFlag eq 0 THEN GuiShowLabel, ImgObj

END


;;	PRO GuiOptionChange
;;	 Handle changes to calibration options widget display
PRO GuiOptionChange
@cisscal_common.pro	; include COMMON definitions
  WIDGET_CONTROL,GuiOptionsGrp,GET_VALUE=GuiOptionVal

  for i=0,9 do begin
      if i eq GuiOptionVal then begin
          WIDGET_CONTROL,GuiParamsPage[i],MAP=1
      endif else begin
          WIDGET_CONTROL,GuiParamsPage[i],MAP=0
      endelse
  endfor
END


;;	PRO GuiOnOffChange
;;	 Turn calibration options on and off
PRO GuiOnOffChange
@cisscal_common.pro	; include COMMON definitions
  WIDGET_CONTROL,GuiOnOffGrp,GET_VALUE=GuiOnOffVal
  WIDGET_CONTROL,BiasGrp,GET_VALUE=biasmode

  (*(*CalOptions).lutc).onoff = GuiOnOffVal[0]
  (*(*CalOptions).bitw).onoff = GuiOnOffVal[1]
  (*(*CalOptions).bias).onoff = GuiOnOffVal[2]

  if GuiOnOffVal[2] eq 0 then $
     (*(*CalOptions).twohz).onoff = GuiOnOffVal[2]
  if GuiOnOffVal[2] eq 1 and biasmode gt 0 then $
     (*(*CalOptions).twohz).onoff = GuiOnOffVal[2]

  (*(*CalOptions).dark).onoff = GuiOnOffVal[3]
  (*(*CalOptions).abpp).onoff = GuiOnOffVal[4]
  (*(*CalOptions).lin).onoff = GuiOnOffVal[5]
  (*(*CalOptions).flat).onoff = GuiOnOffVal[6]
  (*(*CalOptions).flux).onoff = GuiOnOffVal[7]
  (*(*CalOptions).corr).onoff = GuiOnOffVal[8]
  (*(*CalOptions).geom).onoff = GuiOnOffVal[9]

END

;;      PRO LogLevelChange
;;       Handle change in log (DebugFlag) level:
;;        0 = no logging
;;        1 = log some messages
;;        2 = log all messages
;
;        (Added 11/04 by Ben Knowles)
PRO LogLevelChange_Event, event
@cisscal_common.pro	; include COMMON definitions

  common ll, loglevels

  widget_control,event.id,get_uvalue=uval
  if uval eq 'ChangeLog' then begin
      DebugFlag = event.value
      if DebugFlag gt 0 then begin
         CISSCAL_Log
         CISSCAL_Log,'Log level set to '+loglevels[DebugFlag]
      endif
  endif
  widget_control, event.top, /destroy
END

PRO LogLevelChange, ev
@cisscal_common.pro	; include COMMON definitions

  common ll, loglevels

  loglevels = ['0: No message logging', $
               '1: Standard message logging',$
               '2: All messages logged']

  tlb = widget_base(title='Select Log Level', column=1,$
                  group_leader=ev.top, /floating)

  LogLevGrp = CW_BGROUP(tlb, loglevels, /EXCLUSIVE, /NO_RELEASE, $
                  SET_VALUE=DebugFlag, UVALUE='ChangeLog')

  cancel = widget_button(tlb,value = 'Cancel',uvalue='Cancel')

  widget_control, tlb, /realize
  xmanager, 'LogLevelChange', tlb
END

;        PRO SatMissPixelChange
;          Handle output pixel values in GUI
PRO SatMissPixelChange_Event, event
@cisscal_common.pro

widget_control,event.id,get_uvalue=uval
widget_control,event.id,get_value=val
if uval eq 'SatPix' then begin
   satval = strupcase(strtrim(val,2))
   if (strupcase(satval) eq 'NAN') then satflt = !values.f_nan else if $
      (satval eq '' or satval eq 'NULL') then satflt = !values.f_infinity else $
         satflt = float(satval)
   (*(*CalOptions).defval).saturated = satflt
endif else if uval eq 'MissPix' then begin
   missval = strupcase(strtrim(val,2))
   if (strupcase(missval) eq 'NAN') then missval = !values.f_nan else if $
      missval eq '' then missval = 0.0 else $
         missval = float(missval)
   (*(*CalOptions).defval).missing = missval
endif

widget_control, event.top, /destroy

END

PRO SatMissPixelChange, ev
@cisscal_common.pro

  tlb = widget_base(title='Output Pixel Values', column=1,$
                    group_leader=ev.top, /floating)

  SatBase = widget_base(tlb,/column,xpad=0,ypad=0)
  SatLabel = widget_label(SatBase,value='Saturated pixels [NAN, value, or null (no change)]:',/align_right)

  if (*(*CalOptions).defval).saturated eq !values.f_infinity then stext = '' else $
     stext = strtrim(string((*(*CalOptions).defval).saturated),2)

  SatText = widget_text(SatBase,value = stext,/edit,uvalue = 'SatPix')

  MissBase = widget_base(tlb,/column,xpad=0,ypad=0)
  MissLabel = widget_label(MissBase,value='Missing pixels [NAN, value]:',/align_right)
  MissText = widget_text(MissBase,value = strtrim(string((*(*CalOptions).defval).missing),2),/edit,$
                        uvalue = 'MissPix')
 
  cancel = widget_button(tlb,value='Cancel',uvalue='Cancel')

  widget_control, tlb, /realize
  xmanager, 'SatMissPixelChange', tlb
END

;;	PRO GuiSelectDark
;;	 Handle selection of dark file to be subtracted
;;	(Added 4/02 by Ben Knowles)
PRO GuiSelectDark
@cisscal_common.pro	; include COMMON definitions

  if (*(*CalOptions).dark).darkfile eq '' then begin
      selectdarkpath = ImageBaseDir
  endif else begin
      lastslash = strpos((*(*CalOptions).dark).darkfile,'/',$
                         /reverse_search)
      selectdarkpath = strmid((*(*CalOptions).dark).darkfile,0,lastslash)
  endelse

  GuiPrint, 'Select a dark file...'
  SelectDarkFile = DIALOG_PICKFILE(/READ, FILTER='*', $
	TITLE='Select dark file', PATH=SelectDarkPath)

  if SelectDarkFile ne '' then begin
      (*(*CalOptions).dark).darkfile = SelectDarkFile
      GuiPrint, 'Dark selected: ' + SelectDarkFile
  endif
END

;;	PRO GuiSelectMask
;;	 Handle selection of mask file for 2 Hz noise removal
;
;	(Added 12/03 by Ben Knowles)
PRO GuiSelectMask
@cisscal_common.pro	; include COMMON definitions

  if (*(*(*CalOptions).twohz).imagemean).maskfile eq '' then begin
      selectmaskpath = ''
  endif else begin
      lastslash = strpos((*(*(*CalOptions).twohz).imagemean).maskfile,'/',$
                         /reverse_search)
      selectmaskpath = strmid((*(*(*CalOptions).twohz).imagemean).maskfile,$
                              0,lastslash)
  endelse

  GuiPrint, 'Select a mask file...'
  SelectMaskFile = DIALOG_PICKFILE(/READ, FILTER='*', $
	TITLE='Select mask file', PATH=SelectMaskPath, $
	GET_PATH=SelectMaskPath)
  if SelectMaskFile ne '' then begin
      (*(*(*CalOptions).twohz).imagemean).maskfile = SelectMaskFile
      GuiPrint, 'Mask file selected: ' + SelectMaskFile
  endif
END

;;	PRO GuiSelectMissing
;;	 Handle selection of missing pixel file for 2 Hz noise removal
;
;	(Added 12/03 by Ben Knowles)
PRO GuiSelectMissing, ImgObj
@cisscal_common.pro	; include COMMON definitions

  if (*(*(*CalOptions).twohz).imagemean).missingfile eq '' then begin
      selectmissingpath = ''
  endif else begin
      lastslash = strpos((*(*(*CalOptions).twohz).imagemean).missingfile,'/',$
                         /reverse_search)
      selectmissingpath = strmid((*(*(*CalOptions).twohz).imagemean).missingfile,$
                              0,lastslash)
  endelse

  GuiPrint, 'Select a missing pixel file...'
  SelectMissingFile = DIALOG_PICKFILE(/READ, FILTER='*', $
	TITLE='Select missing pixel file', PATH=SelectMissingPath, $
	GET_PATH=SelectMissingPath)
  if SelectMissingFile ne '' then begin
      (*(*(*CalOptions).twohz).imagemean).missingfile = SelectMissingFile

    ; read in mask array and stick in self.MissingP:
      MissingObj = OBJ_NEW('CassImg')
      MissingObj->ReadVic, SelectMissingFile, /Quiet, /NotCass
      missing = float(MissingObj->Image())
      OBJ_DESTROY, MissingObj    ; Finished with object: reclaim the space
      
      ImgObj->SetMissing,missing
      GuiPrint, 'Missing pixel file loaded: ' + SelectMissingFile
  endif
END

;;	PRO GuiSelectSpec
;;	 Handle selection of spectral file for I/F
;
;	(Added 12/03 by Ben Knowles)
PRO GuiSelectSpec
@cisscal_common.pro	; include COMMON definitions

  if (*(*(*CalOptions).flux).ioverf).specfile eq '' then begin
      selectspecpath = ''
  endif else begin
      lastslash = strpos((*(*(*CalOptions).flux).ioverf).specfile,'/',$
                         /reverse_search)
      selectspecpath = strmid((*(*(*CalOptions).flux).ioverf).specfile,$
                              0,lastslash)
  endelse

  GuiPrint, 'Select a spectral file...'
  SelectSpecFile = DIALOG_PICKFILE(/READ, FILTER='*', $
	TITLE='Select spectral file', PATH=SelectSpecPath, $
	GET_PATH=SelectSpecPath)
  if SelectSpecFile ne '' then begin
      (*(*(*CalOptions).flux).ioverf).specfile = SelectSpecFile
      GuiPrint, 'Spectral file loaded: ' + SelectSpecFile
  endif
END


;*****************************************************************************
;;
;;	GUI coordination procedures...
;;
;;	PRO CisscalGui_Event
;;	 Top level event handler:
;;	 Process event messages received from the main GUI handler,
;;	  dispatching the routines that actually do things
;
PRO CisscalGui_Event, ev
@cisscal_common.pro	; include COMMON definitions

; Comment out for debugging:
;  CATCH, GuiException
;  IF GuiException NE 0 THEN BEGIN
;    PRINT, 'Noted exception ' + STRING(GuiException) + ' (' + !ERR_STRING + ')'
;    RETURN
;  END

  WIDGET_CONTROL, ev.top, GET_UVALUE=pstruct, /no_copy
  WIDGET_CONTROL, ev.id, GET_UVALUE=MyWidget

  WIDGET_CONTROL, WIDGET_INFO(ev.handler, /CHILD), GET_UVALUE=ImgObj

  CASE MyWidget OF
    'Batch' : Cisscal_BatchGui, ImgObj, ev
    'FileOpen' : BEGIN
	NewImgObj = GuiOpenFile(ImgObj)
	IF OBJ_VALID(NewImgObj) THEN msens = 1 ELSE msens = 0
	WIDGET_CONTROL, WIDGET_INFO(ev.handler, /CHILD), SET_UVALUE=NewImgObj
	ImageWinValid = 0
        IBatch = -1
        (*(*(*CalOptions).twohz).imagemean).maskfile = ''
        widget_control, pstruct.twohz_im_mask_show, sensitive=msens
        GuiEnabMenuOpts,msens
        END
    'FileSave' : GuiSaveFile, ImgObj
    'FileLoadOpts' : BEGIN
       optionsfile = DIALOG_PICKFILE(FILTER='*.txt',$                                   
                                      TITLE='Load Calibration Options File', $
                                      PATH=CisscalDir)

       if file_test(optionsfile) then begin
          
          optsarr = cisscal_readoptfile(optionsfile,suffixes=suffix,bmode=biasmode)
          (*BatchParams).outputext = suffix
          CalOptions = ptr_new(optsarr)
          
          if DebugFlag gt 0 then Cisscal_Log,'Loaded calibration options file '+optionsfile
          
          ;onoff:
          WIDGET_CONTROL,GuiOnOffGrp,SET_VALUE=[(*(*CalOptions).lutc).onoff,$
                                                (*(*CalOptions).bitw).onoff,$
                                                (*(*CalOptions).bias).onoff,$
                                                (*(*CalOptions).dark).onoff,$
                                                (*(*CalOptions).abpp).onoff,$
                                                (*(*CalOptions).lin).onoff,$
                                                (*(*CalOptions).flat).onoff,$
                                                (*(*CalOptions).flux).onoff,$
                                                (*(*CalOptions).corr).onoff,$
                                                (*(*CalOptions).geom).onoff]

          widget_control, BiasGrp, set_value=biasmode
          widget_control, pstruct.twohz_im_base,sensitive=(*(*(*CalOptions).twohz).imagemean).onoff
          widget_control, pstruct.twohz_im_maskfile, $
                          set_value=(*(*(*CalOptions).twohz).imagemean).maskfile
          if (*(*(*CalOptions).twohz).imagemean).maskfile eq '' then begin
             widget_control,pstruct.twohz_im_mask_page[0],map=1
             widget_control,pstruct.twohz_im_mask_page[1],map=0
          endif else begin
             widget_control,pstruct.twohz_im_mask_page[0],map=0
             widget_control,pstruct.twohz_im_mask_page[1],map=1
          endelse
          widget_control, pstruct.twohz_im_mask_threshold, $
                          set_value=strtrim(string((*(*(*CalOptions).twohz).imagemean).threshold),2)
          widget_control, pstruct.twohz_im_mask_pixrange, $
                          set_value=strtrim(string((*(*(*CalOptions).twohz).imagemean).pixrange),2)
          ;dark:
          if (*(*CalOptions).dark).darkfile eq '' then begin
             widget_control, pstruct.dark_opts, set_value=0
             widget_control, pstruct.dark_opts_page[0], map=1
             widget_control, pstruct.dark_opts_page[1], map=0
          endif else begin
             widget_control, pstruct.dark_opts, set_value=1
             widget_control, pstruct.dark_opts_page[0], map=0
             widget_control, pstruct.dark_opts_page[1], map=1
             widget_control, pstruct.dark_file, set_value=(*(*CalOptions).dark).darkfile
          endelse
          widget_control,pstruct.dark_opts_hot,set_value=(*(*CalOptions).dark).hotpix
          
          ;abpp:
          widget_control, pstruct.abpp_threshold, $
                          set_value=strtrim(string((*(*CalOptions).abpp).threshold),2)
          ;flux:
          widget_control, pstruct.flux_iof, set_value=(*(*(*CalOptions).flux).ioverf).onoff
          widget_control, pstruct.flux_opts_page[0], map=(*(*(*CalOptions).flux).ioverf).onoff eq 0
          widget_control, pstruct.flux_opts_page[1], map=(*(*(*CalOptions).flux).ioverf).onoff eq 1
          widget_control, pstruct.flux_int_opts,set_value=$
                          [(*(*CalOptions).flux).gain_onoff,(*(*CalOptions).flux).expt_onoff,$
                           (*(*CalOptions).flux).opta_onoff,(*(*CalOptions).flux).tran_onoff]
          if (*(*(*CalOptions).flux).ioverf).specfile eq '' then begin
             widget_control,pstruct.flux_iof_opts_page[0],map=1
             widget_control,pstruct.flux_iof_opts_page[1],map=0
          endif else begin
             widget_control,pstruct.flux_iof_opts_page[0],map=0
             widget_control,pstruct.flux_iof_opts_page[1],map=1
          endelse
          widget_control, pstruct.flux_iof_specfile, $
                          set_value=(*(*(*CalOptions).flux).ioverf).specfile
          if (*(*(*CalOptions).flux).ioverf).dfs eq -1 then begin
             widget_control, pstruct.flux_iof_dfs_base, sensitive=0
             widget_control, pstruct.flux_iof_dfs, set_value='9.537'
             widget_control, pstruct.flux_iof_dfs_opts, set_value=0
          endif else if (*(*(*CalOptions).flux).ioverf).dfs eq -2 then begin
             widget_control, pstruct.flux_iof_dfs_base, sensitive=0
             widget_control, pstruct.flux_iof_dfs, set_value='5.203'
             widget_control, pstruct.flux_iof_dfs_opts, set_value=1
          endif else begin
             widget_control, pstruct.flux_iof_dfs_base, sensitive=1
             widget_control, pstruct.flux_iof_dfs, $
                             set_value=strtrim(string((*(*(*CalOptions).flux).ioverf).dfs),2)
             widget_control, pstruct.flux_iof_dfs_opts, set_value=2
          endelse
          widget_control, pstruct.corr_time,set_value=(*(*CalOptions).corr).time eq 0   
       endif
    END
    'FileSat' : GuiSatFile, ImgObj
    'FileWriteMiss' : GuiMissFile, ImgObj
    'FileReadMiss' : GuiSelectMissing, ImgObj
    'FileMask' : GuiMaskFile, ImgObj
    'FileQuit': GuiQuit, ev
    'ImgCal' : BEGIN
       GuiImgCal, ImgObj
    END
    'ImgTVIm' : GuiTVIm, ImgObj
    'ImgDisp' : GuiImgDisp, ImgObj
    'ImgDispLog' : GuiImgDisp, ImgObj, /Log
    'ImgDispSqrt' : GuiImgDisp, ImgObj, /Sqrt
    'ImgDispHistEq' : GuiImgDisp, ImgObj, /HistEq
    'ImgDispStretch' : GuiImgDisp, ImgObj, /Stretch
    'ImgSlide' : GuiImgDisp, ImgObj, /Slider
    'ImgSlideLog' : GuiImgDisp, ImgObj, /Log, /Slider
    'ImgSlideSqrt' : GuiImgDisp, ImgObj, /Sqrt, /Slider
    'ImgSlideHistEq' : GuiImgDisp, ImgObj, /HistEq, /Slider
    'ImgSlideStretch' : GuiImgDisp, ImgObj, /Stretch, /Slider
    'ToolsHisto' : GuiToolsHisto, ImgObj
    'ToolsHistoLog' : GuiToolsHisto, ImgObj, /LOG
    'ToolsProfile' : GuiToolsProf, ImgObj
    'ToolsProfAve' : GuiToolsProfAve, ImgObj
    'ToolsInspect' : GuiToolsInspect, ImgObj
    'ShowLabel' : BEGIN
       WIDGET_CONTROL, ev.id, GET_VALUE=ShowLabelStr
       if ShowLabelStr eq 'Show VICAR label' then ShowLabelYes = 1 else ShowLabelYes = 0
       GuiShowLabel, ImgObj
       if ShowLabelYes then WIDGET_CONTROL, ev.id, SET_VALUE='Hide VICAR label' else $
          WIDGET_CONTROL, ev.id, SET_VALUE='Show VICAR label'
    END
    'LogGui': CISSCAL_Log, 'GUI Logging active ' + !STIME, FILENAME='gui'
    'LogOut': CISSCAL_Log, 'GUI Logging active ' + !STIME, FILENAME='stdout'
    'LogErr': CISSCAL_Log, 'GUI Logging active ' + !STIME, FILENAME='stderr'
    'LogFile': BEGIN
        ImPathSz = SIZE(ImPath)
        IF ( ImPathSz[ImPathSz[0]+1] NE 7 ) THEN BEGIN ; if not a string
            ImPath = ImageBaseDir
        ENDIF

        newlogfilename = DIALOG_PICKFILE(TITLE=$
          'Select Log File (messages will be appended)', PATH=ImPath)
        if (strtrim(newlogfilename,2) ne '') then CISSCAL_Log,$
          'GUI Logging active ' + !STIME, FILENAME=newlogfilename
    END
    'LogLev': LogLevelChange, ev
    'SatMiss': SatMissPixelChange, ev
    'GuiOptions' : GuiOptionChange
    'GuiOnOff'   : GuiOnOffChange
    'CalOptions' : BEGIN
        
        widget_control,ev.id,get_value=val

        case ev.id of 

            BiasGrp : begin
               WIDGET_CONTROL,GuiOnOffGrp,GET_VALUE=GuiOnOffVal
               case val of
                  0 : begin     ;BSM
                     (*(*CalOptions).bias).biasstripmean = 1L
                     (*(*CalOptions).twohz).onoff = 0L
                     imsens = 0
                  end
                  1 : begin     ;OC
                     (*(*CalOptions).bias).biasstripmean = 0L
                     if GuiOnOffVal[2] eq 1 then (*(*CalOptions).twohz).onoff = 1L
                     (*(*(*CalOptions).twohz).imagemean).onoff = 0L
                     imsens = 0
                  end
                  2 : begin     ;IM
                     (*(*CalOptions).bias).biasstripmean = 1L
                     if GuiOnOffVal[2] eq 1 then (*(*CalOptions).twohz).onoff = 1L
                     (*(*(*CalOptions).twohz).imagemean).onoff = 1L
                     imsens = 1
                  end
               endcase
               widget_control,pstruct.twohz_im_base,sensitive=imsens
            end

            pstruct.twohz_im_maskopts : begin
                if val eq 0 then begin
                    widget_control,pstruct.twohz_im_mask_page[0],map=1
                    widget_control,pstruct.twohz_im_mask_page[1],map=0
                    (*(*(*CalOptions).twohz).imagemean).maskfile = ''
                endif else begin
                    widget_control,pstruct.twohz_im_mask_page[0],map=0
                    widget_control,pstruct.twohz_im_mask_page[1],map=1
                endelse
            end

            pstruct.twohz_im_mask_threshold : begin
                (*(*(*CalOptions).twohz).imagemean).threshold = val
            end

            pstruct.twohz_im_mask_pixrange : begin
                (*(*(*CalOptions).twohz).imagemean).pixrange = val
            end

            pstruct.dark_opts : begin
                if val eq 0 then begin 
                    (*(*CalOptions).dark).darkfile = ''
                     widget_control,pstruct.dark_opts_page[1],map=0
                     widget_control,pstruct.dark_opts_page[0],map=1
                endif else if val eq 1 then begin
                     widget_control,pstruct.dark_opts_page[0],map=0
                     widget_control,pstruct.dark_opts_page[1],map=1
                     widget_control,pstruct.dark_file,get_value=darkval
                     (*(*CalOptions).dark).darkfile = darkval
                endif
            end

            pstruct.dark_opts_hot : begin
               (*(*CalOptions).dark).hotpix = val
            end

            pstruct.abpp_threshold : begin
                (*(*CalOptions).abpp).threshold = val                 
            end

            pstruct.flux_iof : begin
                (*(*(*CalOptions).flux).ioverf).onoff = val
                if val eq 0 then begin
                   widget_control,pstruct.flux_opts_page[0],map=1
                   widget_control,pstruct.flux_opts_page[1],map=0
                endif else begin
                   widget_control,pstruct.flux_opts_page[0],map=0
                   widget_control,pstruct.flux_opts_page[1],map=1
                endelse
            end

            pstruct.flux_int_opts : begin
               (*(*CalOptions).flux).gain_onoff = val[0]
               (*(*CalOptions).flux).expt_onoff = val[1]
               (*(*CalOptions).flux).opta_onoff = val[2]
               (*(*CalOptions).flux).tran_onoff = val[3]
            end

            pstruct.flux_iof_opts : begin
                if val eq 0 then begin
                    widget_control,pstruct.flux_iof_opts_page[0],map=1
                    widget_control,pstruct.flux_iof_opts_page[1],map=0
                    (*(*(*CalOptions).flux).ioverf).specfile = ''
                endif else begin
                    widget_control,pstruct.flux_iof_opts_page[0],map=0
                    widget_control,pstruct.flux_iof_opts_page[1],map=1
                    widget_control,pstruct.flux_iof_specfile,get_value=specval
                    (*(*(*CalOptions).flux).ioverf).specfile = specval
                endelse                
            end

            pstruct.flux_iof_dfs_opts : begin
                if val eq 2 then begin
                    widget_control,pstruct.flux_iof_dfs_base,sensitive=1
                endif else begin
                    widget_control,pstruct.flux_iof_dfs_base,sensitive=0
                    if val eq 0 then begin
                        dfs_code = -1 ;saturn
                        dfs_val = '9.577'
                    endif
                    if val eq 1 then begin
                        dfs_code = -2 ;jupiter
                        dfs_val = '5.046'
                    endif
                    (*(*(*CalOptions).flux).ioverf).dfs = dfs_code
                    widget_control,pstruct.flux_iof_dfs,set_value=dfs_val
                endelse
            end

            pstruct.flux_iof_dfs : begin
                (*(*(*CalOptions).flux).ioverf).dfs = float(val)
            end

            pstruct.corr_time : begin
               if val eq 1 then begin
                  (*(*CalOptions).corr).time = 0l
               endif else begin
                  (*(*CalOptions).corr).time = 1L
               endelse
            end
            
            else : PRINT,'Event widget ID has unexpected value:',ev.id
        endcase
    END
    'DarkSelect' : BEGIN
       GuiSelectDark
       val = (*(*CalOptions).dark).darkfile
       widget_control,pstruct.dark_file,set_value=val
    END
    'MaskSelect' : BEGIN
       GuiSelectMask
       val = (*(*(*CalOptions).twohz).imagemean).maskfile
       widget_control,pstruct.twohz_im_maskfile,set_value=val
       if val ne '' then widget_control,pstruct.twohz_im_mask_show, sensitive=1
    END
    'SpecSelect' : BEGIN
       GuiSelectSpec
       val = (*(*(*CalOptions).flux).ioverf).specfile
       widget_control,pstruct.flux_iof_specfile,set_value=val
    END
    'ShowMask' : BEGIN
        if (*(*(*CalOptions).twohz).imagemean).maskfile ne '' then begin
            IF DebugFlag gt 0 THEN CISSCAL_Log, 'Displaying user-specified mask file.'
            maskfile = (*(*(*CalOptions).twohz).imagemean).maskfile

            MaskObj = OBJ_NEW('CassImg')
            
            MaskObj->ReadVic, maskfile, /Quiet, /NotCass
            mask = float(MaskObj->Image())
            
            OBJ_DESTROY, MaskObj ; Finished with object: reclaim the space
        endif else begin
            tempimage = ImgObj->Image()

           ; quick calibration (de-lut and bias removal):

            bias = (ImgObj->GetOffset())[0]

            if ImgObj->GetCalibrated() lt 1 and $
               ImgObj->GetConvType() eq 'TABLE' then begin
                  tempimage = cisscal_delut(tempimage)
                  bias = cisscal_delut(fix(bias))
            endif
               
            if ImgObj->GetCalibrated() lt 3 then tempimage = temporary(tempimage - bias)

            thresh = (*(*(*CalOptions).twohz).imagemean).threshold
            pixrange = (*(*(*CalOptions).twohz).imagemean).pixrange

            mask = float(tempimage gt thresh)
            mask = float(smooth(mask,pixrange,/edge_truncate) gt (0.5/(pixrange^2)))
            mask = float(smooth(mask,pixrange,/edge_truncate) gt 0.25)
        endelse

        GuiImgDisp, ImgObj, mask=mask

     END
    'PlotOverclocks' : GuiPlotOverclocks, ImgObj
    'HlpAbt' : GuiHelpAbout
    'LabelDone' : WIDGET_CONTROL, ev.top, /DESTROY
    'InspDone' : WIDGET_CONTROL, ev.top, /DESTROY
    ELSE: PRINT,'MyWidget has unexpected value:',MyWidget
  ENDCASE

  ; shutdown exception fixed by Shawn Ewald with following if statement:
  IF (WIDGET_INFO(ev.top, /VALID_ID)) THEN $
     widget_control, ev.top, set_uvalue=pstruct,/no_copy

END

;;	PRO GraphWin_Event
;;	 Graphics windows event handler:
;;	 Process event messages received from the graphics window widgets,
;;	  despatching the routines that actually do things
PRO GraphWin_Event, ev
@cisscal_common.pro	; include COMMON definitions

  CATCH, WinException
  IF WinException NE 0 THEN BEGIN
    HELP,CALLS=A
    PRINT, 'Noted exception ' + STRING(WinException) + ' (' + !ERR_STRING + ')'
    PRINT,' at ' + A[0] + ' from ' + A[1]
    RETURN
  END

;	Retreive the image object stashed in the base widget's UVALUE
  WIDGET_CONTROL, ev.top, GET_UVALUE=ImgObj

  WIDGET_CONTROL, ev.id, GET_UVALUE=WinWidget

  CASE WinWidget OF
    'PrintImg' : GuiPrintImage
    'PrintHisto' : GuiToolsHisto, ImgObj, /PRINT
    'PrintHistoLog' : GuiToolsHisto, ImgObj, /PRINT, /LOG
    'PrintProfile' : GuiToolsProf, ImgObj, /PRINT
    'PrintProfAve' : GuiToolsProfAve, ImgObj, /PRINT
    'PrintOverclocks' : GuiPlotOverclocks, ImgObj, /PRINT
    'PrintNoGraph' : RETURN	; This window is not yet in use
    'WinDone' : WIDGET_CONTROL, ev.top, /DESTROY
   ELSE: PRINT,'WinWidget has unexpected value:',WinWidget
  ENDCASE
END


;************************************************************************
;;
;;	PRO CISSCal_Gui
;;	 Top level procedure to build the GUI widget tree,
;;	  do various initialisation, and make the GUI active
;
PRO CISSCal_Gui, Restart=Restart
@cisscal_common.pro	; include COMMON definitions

  CisscalVers = '4.1'  ; VERSION NUMBER

;  !ORDER = 1	; Display images top-to-bottom rather than vice-versa

  IBatch = -1   ; Do not start in batch mode
  DebugFlag = 1 ; Default setting - intermediate logging

  IF(XREGISTERED('CisscalGui') NE 0) THEN BEGIN
    PRINT,'CisscalGui is already running, and is single threaded only'
    IF NOT KEYWORD_SET(Restart) THEN RETURN
;	The following doesn't actually seem to work- the idea had been
;	to kill and restart the GUI to recover from an error break
    WIDGET_CONTROL, GuiBase, /DESTROY
  END

;	Set up a base widget with a menubar
;	with a child text widget for messages (not editable)
;	(the latter also ensures that the base is wide enough for the title)
  GuiBase = WIDGET_BASE(MBAR=MenuBar, $
                        TITLE='CISSCAL: Cassini ISS Calibration Tool v'+CisscalVers,/COLUMN,xpad=0,ypad=0)
  GuiUpperBase = WIDGET_BASE(GuiBase, /ROW, FRAME=1,xpad=0,ypad=0)
  GuiTextBase = WIDGET_BASE(GuiUpperBase, /COLUMN, xpad=0,ypad=0)
  GuiLogLbl = WIDGET_LABEL(GuiTextBase, VALUE='Log window')
  GuiText = WIDGET_TEXT(GuiTextBase, XSIZE=85, YSIZE=47, /SCROLL)
;  GuiText = WIDGET_TEXT(GuiTextBase, SCR_XSIZE=13, SCR_YSIZE=13, UNITS=2, /SCROLL)
  GuiButtonsBase = WIDGET_BASE(GuiUpperBase,/COLUMN)

;*********************************
; Initialize Batch Mode Parameters
;*********************************

  params  = {                                     $
             inputdir    : '',                    $
             inputtype   : 0l,                    $
             inputregexp : '*.IMG',               $ ; use if inputtype = 0
             inputlist   : '',                    $ ; use if inputtype = 1
             outputdir   : '',                    $
             outputext   : '.IMG.cal',            $
             outdirin    : 0l,                    $
             dark        : ptr_new({uselist : 0l, $
                                    dir     : '', $
                                    list    : '', $
                                    names   : ptr_new()})}

  BatchParams = ptr_new(params)

;********************
; Calibration Options
;********************

  optsarr = cisscal_readoptfile(CisscalDir+'cisscal_default_options.txt',suffixes=suffix,bmode=biasmode)
  (*BatchParams).outputext = suffix
  CalOptions = ptr_new(optsarr)

  GuiOptionList = ['LUT conversion','Bit-weight correction',$       ;'Subtract bias',  $
                   'Subtract Bias/2Hz noise','Subtract Dark','A-B Pixel pairs', $
                   'Linearize','Flatfield','Convert DN to flux','Absolute correction', $
                   'Geometric correction']

  GuiOnOffList = [(*(*CalOptions).lutc).onoff,(*(*CalOptions).bitw).onoff,$
                  (*(*CalOptions).bias).onoff,$
                  (*(*CalOptions).dark).onoff,(*(*CalOptions).abpp).onoff,$
                  (*(*CalOptions).lin).onoff,(*(*CalOptions).flat).onoff,$
                  (*(*CalOptions).flux).onoff,(*(*CalOptions).corr).onoff,$
                  (*(*CalOptions).geom).onoff]

  GuiOnOffText = [' ',' ',' ',' ',' ',' ',' ',' ',' ',' ']

  GuiOptionsLabel = widget_label(GuiButtonsBase,value = 'Calibration Options')

  GuiRowBase = WIDGET_BASE(GuiButtonsBase,/ROW,/FRAME,xpad=0,ypad=0)
  GuiOnOffBase = WIDGET_BASE(GuiRowBase,/COLUMN,xpad=0,ypad=0)
  GuiOptionBase = WIDGET_BASE(GuiRowBase,/COLUMN,xpad=0,ypad=0)
  GuiOnOffGrp = CW_BGROUP(GuiOnOffBase, GuiOnOffText, /NONEXCLUSIVE, $
                          UVALUE='GuiOnOff',SET_VALUE=GuiOnOffList,LABEL_TOP='On/Off')
  GuiOptionsGrp = CW_BGROUP(GuiOptionBase, GuiOptionList, /EXCLUSIVE, /NO_RELEASE,$
                  LABEL_TOP='Show Parameters', UVALUE='GuiOptions', SET_VALUE=0)

  GuiParamsLabel = widget_label(GuiButtonsBase,value = 'Option Parameters')
  
  GuiParamsBase = widget_base(GuiButtonsBase,frame=1)

  GuiParamsPage = lonarr(10)

  GuiParamsPage[0] = WIDGET_BASE(GuiParamsBase,/COLUMN,map=1)
  GuiParamsPage[1] = WIDGET_BASE(GuiParamsBase,/COLUMN,map=0)
  GuiParamsPage[2] = WIDGET_BASE(GuiParamsBase,/COLUMN,map=0)
  GuiParamsPage[3] = WIDGET_BASE(GuiParamsBase,/COLUMN,map=0)
  GuiParamsPage[4] = WIDGET_BASE(GuiParamsBase,/COLUMN,map=0)
  GuiParamsPage[5] = WIDGET_BASE(GuiParamsBase,/COLUMN,map=0)
  GuiParamsPage[6] = WIDGET_BASE(GuiParamsBase,/COLUMN,map=0)
  GuiParamsPage[7] = WIDGET_BASE(GuiParamsBase,/COLUMN,map=0)
  GuiParamsPage[8] = WIDGET_BASE(GuiParamsBase,/COLUMN,map=0)
  GuiParamsPage[9] = WIDGET_BASE(GuiParamsBase,/COLUMN,map=0)
  
  ; 1: LUT conversion:

   lutc_plabel = widget_label(guiparamspage[0],value = '(No adjustable parameters)')

  ; 2: bitweight correction:

   bitw_plabel = widget_label(guiparamspage[1],value = '(No adjustable parameters)')

  ; 3: Bias and 2 Hz removal:

  BiasGrp = cw_bgroup(guiparamspage[2], ['Constant Bias','Overclocked pixels','Image Mean'], $
                      set_value=biasmode, /no_release, /exclusive, /column, $
                      uvalue='CalOptions')

  twohz_im_bkgd = widget_base(guiparamspage[2], /row, space=15)  ; this creates an indent
  twohz_im_dummy = widget_base(twohz_im_bkgd)
  twohz_im_base = widget_base(twohz_im_bkgd, /column, $
                              sensitive=(*(*(*CalOptions).twohz).imagemean).onoff,xpad=0,ypad=0)

  maskfile_val = (*(*(*CalOptions).twohz).imagemean).maskfile
  if maskfile_val eq '' then mask_toggle=0 else mask_toggle=1

  twohz_im_maskopts = cw_bgroup(twohz_im_base, ['Auto Mask','Choose Mask File'], $
                                set_value=mask_toggle, /no_release, /exclusive, /column, $
                                uvalue='CalOptions')

  twohz_im_mask_base = widget_base(twohz_im_base, /column,xpad=0,ypad=0)

  twohz_im_mask_base_top = widget_base(twohz_im_mask_base,xpad=0,ypad=0)
  twohz_im_mask_base_bot = widget_base(twohz_im_mask_base,xpad=0,ypad=0)

  twohz_im_mask_page = lonarr(2)

  twohz_im_mask_page[0] = widget_base(twohz_im_mask_base_top,/column,map=mask_toggle eq 0,xpad=0,ypad=0)
  twohz_im_mask_page[1] = widget_base(twohz_im_mask_base_top,/column,map=mask_toggle eq 1,xpad=0,ypad=0)

  twohz_im_mask_auto_base1 = widget_base(twohz_im_mask_page[0],/row,xpad=0,ypad=0)
  twohz_im_mask_auto_base2 = widget_base(twohz_im_mask_page[0],/row,xpad=0,ypad=0)

  twohz_im_mask_threshold_label = widget_label(twohz_im_mask_auto_base1, value='Threshold',$
                                               /align_left)
  threshold_val = string(format='(F7.2)',(*(*(*CalOptions).twohz).imagemean).threshold)
  twohz_im_mask_threshold = widget_text(twohz_im_mask_auto_base1, value = threshold_val,$
                                        xsize=7, /edit, uvalue='CalOptions')

  twohz_im_mask_pixrange_label = widget_label(twohz_im_mask_auto_base2, value='Pixel Range',$
                                               /align_left)
  pixrange_val = string(format='(F7.2)',(*(*(*CalOptions).twohz).imagemean).pixrange)
  twohz_im_mask_pixrange = widget_text(twohz_im_mask_auto_base2, value = pixrange_val,$
                                        xsize=7, /edit, uvalue='CalOptions')

  twohz_im_maskfile_button = widget_button(twohz_im_mask_page[1], value='Browse...',$
                                            uvalue='MaskSelect')
  twohz_im_maskfile = widget_text(twohz_im_mask_page[1], value=maskfile_val)

  twohz_im_mask_show = widget_button(twohz_im_mask_base_bot, value='Show mask...',$
                                     uvalue='ShowMask',sensitive=mask_toggle)

  ; 5: dark subtraction:

  darkfile_val = (*(*CalOptions).dark).darkfile
  if darkfile_val eq '' then dark_toggle=0 else dark_toggle=1

  dark_opts = cw_bgroup(guiparamspage[3], ['Use Dark Model',$
                       'Choose File'], set_value=dark_toggle, /no_release, /exclusive, /row, $
                       uvalue='CalOptions')

  dark_opts_base = widget_base(guiparamspage[3],xpad=0,ypad=0)

  dark_opts_page = lonarr(2)

  dark_opts_page[0] = widget_base(dark_opts_base,/column,map=dark_toggle eq 0,xpad=0,ypad=0,xoffset=40)
  dark_opts_page[1] = widget_base(dark_opts_base,/column,map=dark_toggle eq 1,xpad=0,ypad=0,xoffset=40)

  dark_opts_label = widget_label(dark_opts_page[0],value='Dark model options')
  dark_opts_hot = cw_bgroup(dark_opts_page[0],'Remove hot pixels',$
                            set_value=(*(*CalOptions).dark).hotpix,$
                            /nonexclusive,uvalue='CalOptions')

  dark_file_button = widget_button(dark_opts_page[1],value='Browse...',uvalue='DarkSelect')
  dark_file = widget_text(dark_opts_page[1], value=darkfile_val)

  ; 6: pixel pair correction:

  abpp_base = widget_base(guiparamspage[4],/row,xpad=0,ypad=0)

  abpp_threshold_label = widget_label(abpp_base, value='Threshold',$
                                               /align_left)
  abpp_threshold_val = string(format='(F7.2)',(*(*CalOptions).abpp).threshold)
  abpp_threshold = widget_text(abpp_base, value = abpp_threshold_val,$
                               xsize=7, /edit, uvalue='CalOptions')

  ; 7: linearize:

   lin_plabel = widget_label(guiparamspage[5],value = '(No adjustable parameters)')

  ; 8: flatfield:

   flat_plabel = widget_label(guiparamspage[6],value = '(No adjustable parameters)')

  ; 9: convert to flux:

  flux_iof = cw_bgroup(guiparamspage[7], ['Intensity units','I/F (unitless)'], $
                       set_value=(*(*(*CalOptions).flux).ioverf).onoff, /no_release, $
                       /exclusive, /row, uvalue='CalOptions')

  flux_opts_base = widget_base(guiparamspage[7], xpad=0,ypad=0)

  flux_opts_page = lonarr(2)

  flux_opts_page[0] = widget_base(flux_opts_base, /column,map=(*(*(*CalOptions).flux).ioverf).onoff eq 0,$
                                  xpad=0,ypad=0,xoffset=10)
  flux_opts_page[1] = widget_base(flux_opts_base, /column,map=(*(*(*CalOptions).flux).ioverf).onoff eq 1,$
                                  xpad=0,ypad=0,xoffset=10)

  flux_int_label = widget_label(flux_opts_page[0], value='Intensity Options')

  flux_int_opts = cw_bgroup(flux_opts_page[0],['Multiply by gain','Divide by exposure time',$
                            'Divide by optics area/solid angle','Divide by optical and quantum eff.'],$
                            set_value=[(*(*CalOptions).flux).gain_onoff,(*(*CalOptions).flux).expt_onoff,$
                                      (*(*CalOptions).flux).opta_onoff,(*(*CalOptions).flux).tran_onoff],$
                            /nonexclusive,/column,uvalue='CalOptions')

  flux_iof_label = widget_label(flux_opts_page[1], value='I/F Options')

  specfile_val = (*(*(*CalOptions).flux).ioverf).specfile
  if specfile_val eq '' then spec_toggle = 0 else spec_toggle = 1

  flux_iof_opts = cw_bgroup(flux_opts_page[1], ['Solar','User-input'], $
                                set_value=spec_toggle, /no_release, /exclusive, /row, $
                                uvalue='CalOptions')

  flux_iof_opts_base = widget_base(flux_opts_page[1],xpad=0,ypad=0)

  flux_iof_opts_page = lonarr(2)

  flux_iof_opts_page[0] = widget_base(flux_iof_opts_base,/column,map=spec_toggle eq 0,xpad=0,ypad=0)
  flux_iof_opts_page[1] = widget_base(flux_iof_opts_base,/column,map=spec_toggle eq 1,xpad=0,ypad=0)

  flux_iof_dfs_label = widget_label(flux_iof_opts_page[0],value='Distance from Sun')

  if (*(*(*CalOptions).flux).ioverf).dfs eq -1 then begin
      dfs_val = '9.577'
      dfs_toggle = 0
      dfs_sens = 0
  endif else if (*(*(*CalOptions).flux).ioverf).dfs eq -2 then begin
      dfs_val = '5.046'
      dfs_toggle = 1
      dfs_sens = 0
  endif else begin
      dfs_val = strtrim(string((*(*(*CalOptions).flux).ioverf).dfs),2) 
      dfs_toggle = 2
      dfs_sens = 1
  endelse

  flux_iof_dfs_opts = cw_bgroup(flux_iof_opts_page[0],$
                                ['Saturn','Jupiter','Specify:'],set_value=dfs_toggle,$
                                /no_release, /exclusive, /column, uvalue='CalOptions')

  flux_iof_dfs_base = widget_base(flux_iof_opts_page[0],sensitive=dfs_sens,/row,xpad=0,ypad=0)

  flux_iof_dfs_label = widget_label(flux_iof_dfs_base,value='Distance from Sun (AU):',$
                                    /align_left)

  flux_iof_dfs = widget_text(flux_iof_dfs_base,value=dfs_val,xsize=5,/edit,$
                             uvalue='CalOptions')

  flux_iof_specfile_button = widget_button(flux_iof_opts_page[1], value='Browse...',$
                                            uvalue='SpecSelect')
  flux_iof_specfile = widget_text(flux_iof_opts_page[1], value=specfile_val)


  ; 10: correction factors:

  corr_time_base = widget_base(guiparamspage[8],/column,xpad=0,ypad=0)

  corr_time_label = widget_label(corr_time_base, value='Sensitivity vs. Time:',/align_left)
  
  if (*(*CalOptions).corr).time eq 0 then corr_time_val = 1 else corr_time_val = 0

  if (!D.NAME eq 'WIN') then newline = string([13B, 10B]) else newline = string(10b)
  
  corr_time = cw_bgroup(corr_time_base,['NAC correction (~8% max)'+newline+$
                                        'WAC correction (~3% max)',$
                                        'No sens vs. time correction'],set_value=corr_time_val,/column,$
                                        /exclusive,/no_release,uvalue='CalOptions',xpad=15)
  
  ;11: geometric correction:

   geom_plabel = widget_label(guiparamspage[9],value = '(No adjustable parameters)')

; Create structure to contain widget button info:

   pstruct = {$
             twohz_im_base           : twohz_im_base,           $
             twohz_im_maskopts       : twohz_im_maskopts,       $
             twohz_im_mask_page      : twohz_im_mask_page,      $
             twohz_im_mask_threshold : twohz_im_mask_threshold, $
             twohz_im_mask_pixrange  : twohz_im_mask_pixrange,  $
             twohz_im_maskfile       : twohz_im_maskfile,       $
             twohz_im_mask_show      : twohz_im_mask_show,      $
             dark_opts               : dark_opts,               $
             dark_opts_page          : dark_opts_page,          $
             dark_opts_hot           : dark_opts_hot,            $
             dark_file               : dark_file,               $
             abpp_threshold          : abpp_threshold,          $
             flux_iof                : flux_iof,                $
             flux_opts_page          : flux_opts_page,          $
             flux_int_opts           : flux_int_opts,           $
             flux_iof_opts           : flux_iof_opts,           $
             flux_iof_opts_page      : flux_iof_opts_page,      $
             flux_iof_dfs_opts       : flux_iof_dfs_opts,       $
             flux_iof_dfs_base       : flux_iof_dfs_base,       $
             flux_iof_dfs            : flux_iof_dfs,            $
             flux_iof_specfile       : flux_iof_specfile,       $
             corr_time               : corr_time                }

;	Now set up menus
  FileMenu = WIDGET_BUTTON(MenuBar, VALUE='File', /MENU)
  FileOpenBtn = WIDGET_BUTTON(FileMenu, VALUE='Open', UVALUE='FileOpen')
  FileSaveBtn = WIDGET_BUTTON(FileMenu, VALUE='Save Image', UVALUE='FileSave')
  FileLoadOptsBtn = WIDGET_BUTTON(FileMenu, VALUE='Load calibration options file', UVALUE='FileLoadOpts')
  FileSatBtn = WIDGET_BUTTON(FileMenu, VALUE='Write saturated pixel file', UVALUE='FileSat')
  FileMaskBtn = WIDGET_BUTTON(FileMenu, VALUE='Write dark sky mask file', UVALUE='FileMask')
  FileWriteMissBtn = WIDGET_BUTTON(FileMenu, VALUE='Write missing pixel file', UVALUE='FileWriteMiss')
  FileReadMissBtn = WIDGET_BUTTON(FileMenu, VALUE='Read missing pixel file', UVALUE='FileReadMiss')
  FileQuitBtn = WIDGET_BUTTON(FileMenu, VALUE='Quit', UVALUE='FileQuit')

  ImageMenu = WIDGET_BUTTON(MenuBar, VALUE='Image', /MENU)
  ImageCalBtn = WIDGET_BUTTON(ImageMenu, VALUE='Calibrate Image', UVALUE='ImgCal')

  ImageDispMenu = WIDGET_BUTTON(ImageMenu, VALUE='View Image', /MENU)
  ImageDispBtn = WIDGET_BUTTON(ImageDispMenu, VALUE='Linear', $
		UVALUE='ImgDisp')
  ImageDispLogBtn = WIDGET_BUTTON(ImageDispMenu, VALUE='Logarithmic', $
		UVALUE='ImgDispLog')
  ImageDispSqrtBtn = WIDGET_BUTTON(ImageDispMenu, VALUE='Square root', $
		UVALUE='ImgDispSqrt')
  ImageDispHEBtn = WIDGET_BUTTON(ImageDispMenu, $
		VALUE='Histogram-equalized', $
		UVALUE='ImgDispHistEq')
  ImageDispStrBtn = WIDGET_BUTTON(ImageDispMenu, $
		VALUE='Range-stretched', $
		UVALUE='ImgDispStretch')

  ImageSlideMenu = WIDGET_BUTTON(ImageMenu, $
	VALUE='View Sliding Image', /MENU)
  ImageSlideBtn = WIDGET_BUTTON(ImageSlideMenu, VALUE='Linear', $
		UVALUE='ImgSlide')
  ImageSlideLogBtn = WIDGET_BUTTON(ImageSlideMenu, VALUE='Logarithmic', $
		UVALUE='ImgSlideLog')
  ImageSlideSqrtBtn = WIDGET_BUTTON(ImageSlideMenu, VALUE='Square root', $
		UVALUE='ImgSlideSqrt')
  ImageSlideHEBtn = WIDGET_BUTTON(ImageSlideMenu, $
		VALUE='Histogram-equalized', $
		UVALUE='ImgSlideHistEq')
  ImageSlideStrBtn = WIDGET_BUTTON(ImageSlideMenu, $
		VALUE='Range-stretched', $
		UVALUE='ImgSlideStretch')

  ToolsMenu = WIDGET_BUTTON(MenuBar, VALUE='Tools', /MENU)
  ToolsHistoBtn = WIDGET_BUTTON(ToolsMenu, VALUE='Histogram', $
		UVALUE='ToolsHisto')
  ToolsHistoLogBtn = WIDGET_BUTTON(ToolsMenu, VALUE='Histogram (log)', $
		UVALUE='ToolsHistoLog')
  ToolsProfileBtn = WIDGET_BUTTON(ToolsMenu, VALUE='Profiles', $
		UVALUE='ToolsProfile')
  ToolsProfAveBtn = WIDGET_BUTTON(ToolsMenu, VALUE='Average profiles', $
		UVALUE='ToolsProfAve')
  ToolsInspectBtn = WIDGET_BUTTON(ToolsMenu, VALUE='Inspect pixel values', $
		UVALUE='ToolsInspect')
  PlotOverclocksBtn = WIDGET_BUTTON(ToolsMenu, VALUE='Plot overclocked pixels', $
                                    UVALUE='PlotOverclocks')

  HelpMenu = WIDGET_BUTTON(MenuBar, VALUE='Help', /MENU, /HELP)
  HelpAboutBtn = WIDGET_BUTTON(HelpMenu, VALUE='About', UVALUE='HlpAbt')

  OptsMenu = WIDGET_BUTTON(MenuBar, VALUE='Options', /MENU)
  ShowLabelBtn = WIDGET_BUTTON(OptsMenu, VALUE='Show VICAR label', UVALUE='ShowLabel')

  LogBtn = WIDGET_BUTTON(OptsMenu, VALUE='Log to...', /MENU)
  LogGuiBtn = WIDGET_BUTTON(LogBtn, VALUE='GUI', UVALUE='LogGui')
  LogOutBtn = WIDGET_BUTTON(LogBtn, VALUE='stdout', UVALUE='LogOut')
  LogErrBtn = WIDGET_BUTTON(LogBtn, VALUE='stderr', UVALUE='LogErr')
  LogFileBtn = WIDGET_BUTTON(LogBtn, VALUE='file...', UVALUE='LogFile')
  LogLevBtn = WIDGET_BUTTON(OptsMenu, VALUE='Set log level...', UVALUE='LogLev')
  SatMissBtn = WIDGET_BUTTON(OptsMenu, VALUE='Saturated and Missing pixels...',UVALUE='SatMiss')

  BatchMenu = WIDGET_BUTTON(MenuBar, VALUE='Batch Mode', /MENU)
  BatchBtn = WIDGET_BUTTON(BatchMenu, VALUE='Calibrate Batch...', UVALUE='Batch')

  GreyableButtons = [ FileSaveBtn, FileSatBtn, FileWriteMissBtn, FileReadMissBtn, $
        FileMaskBtn, ImageCalBtn, ImageDispBtn, ImageDispLogBtn, $
        ImageDispSqrtBtn, ImageDispHEBtn, ImageDispStrBtn, $
	ImageSlideBtn, ImageSlideLogBtn, ImageSlideSqrtBtn, ImageSlideHEBtn, $
        ImageSlideStrBtn, ToolsHistoBtn, ToolsHistoLogBtn, ToolsProfileBtn, ToolsProfAveBtn, $
        ToolsInspectBtn, ShowLabelBtn, PlotOverclocksBtn]
;	ToolsAOIBtn ]   ; Not yet implemented

  GuiEnabMenuOpts,0	; Disable certain menu options until img loaded
  GuiTableBase=-1	; and we don't have a table widget yet
  ShowLabelYes = 0      ; do not show VICAR labels unless asked

;	Assign IDs to the various windows we will use
;	At present, use graphics window 0 for 'TV' image display
  ImageWindow = 0
  HistWindow = 1
  ProfWindow = 2
  ProfAveWindow = 3
  GraphWindow = 4
  OverclkWindow = 5
  ImageWinValid = 0
  GuiWinId =  BYTARR(6)-1	; Set all window numbers to -1 (i.e. invalid)
  GuiWinBase = GuiWinId		; also widget numbers
  GuiWinDraw = GuiWinId
  GuiWinPrint = GuiWinId

; Realize widget:

  WIDGET_CONTROL, GuiBase, /REALIZE

  WIDGET_CONTROL, GuiBase, SET_UVALUE=pstruct, /no_copy

  XMANAGER, 'CisscalGui', GuiBase, /NO_BLOCK
;	Tell CISSCAL_Log to send logging messages to the GUI
  CISSCAL_Log, 'GUI Logging active', FILENAME='gui'

END
