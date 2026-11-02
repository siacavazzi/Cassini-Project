;;	cisscal_common.pro
;;	Common blocks used in radiometric calibration GUI
;;	Kevin Beurle	K.Beurle@qmw.ac.uk	15/9/98
;
;	include as	@cal_gui_common.pro	; include COMMON definitions
;
;	The variables describing GUI widgets worth keeping in scope
;	are grouped in the common block CalibrateGuiCommon
;
;	Common variables added by Ben Knowles, 4/02: 
;		GuiDarkSelect, SelectDarkFile, GuiDarkOpGrp, 
;		GuiDarkOpBase, GuiDarkOpVal
;
;       Totally reorganized (and renamed) by Ben Knowles, 12/03:


COMMON CalibrateGuiCommon, $	; Roots of widget trees, etc.
	GuiBase, GuiTableBase, GuiUpperBase, GuiTextBase, GuiText, CisscalVers

COMMON CalibrateGuiPaths, $	; File path names, etc.
	ImPath, OutImPath, CalibrationBaseDir, ImageBaseDir, CisscalDir

;	Maintain a list of "greyable" buttons
;	These have to be globally visible so that they can be
;	set SENSITIVE or not (i.e. "greyed out") according to whether
;	an image has been loaded yet, etc.
COMMON CalibrateGuiGrey, GreyableButtons

COMMON CalibrateGuiWins, $	          ; Share enumerated window IDs for...
		ImageWindow, $	          ;  the 'TV' image display,
		HistWindow, $	          ;  pixel value histograms
		ProfWindow, ProfAveWindow, $ ;  pixel value profile plots
		GraphWindow, $	          ;  general graphics
                OverclkWindow, $          ;  overclocked pixel plot
		GuiWinId, $	          ;  store ID->window number mapping
		GuiWinBase, GuiWinDraw, $ ;  keep track of assoc'd widgets
		GuiWinPrint

;	Routines using an image cursor (e.g. line/sample profile)
;	need to know if the displayed image is valid
COMMON CalibrateGuiImage, ImageWinValid, GuiImageName

;	Calibration options and compound widgets
COMMON CalibrateGuiOpts, CalOptions, GuiParamsPage, GuiOptionsGrp, DebugFlag, $
        IBatch, GuiOnOffGrp, BatchParams, ShowLabelYes, BiasGrp







