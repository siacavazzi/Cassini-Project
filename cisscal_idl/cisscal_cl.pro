;------------------------------------------
; CISSCAL_CL: CISSCAL Command-line wrapper
;   - Ben Knowles, 5/2006
;------------------------------------------
;Usage:
;
; file - string containing name of single image, or regular
;        expression ('N*' for example) or comma-delineated list of
;        images to be calibrated
;
; optionfile - name of option file to be used; if left blank, will be
;              automatically set to
;              CisscalDir/cisscal_default_options.txt, or user can
;              override optionfile with /default keyword
;   
;     optionfile format key: 
;
;        bias subtraction type:
;              BSM = bias strip mean (default)
;              OC = overclocked pixels
;              IM = image mean
;        flux conversion type:
;              I = intensity units
;              IOF = I/F (default)
;              distance from sun = J (Jupiter), S (Saturn; default), 
;                  AU (manual input in astronomical units)
;
; readlist - string containing name of file with single-column list of
;            images to be calibrated; overrides file option
;
; batchdir - input directory, if not '.'
;
; outputdir - output directory, if not '.'
;
; suffix - extension to add to calibrated image filenames; default is '.IMG.cal'
;
; /default - uses default parameters
;
; Keyword options to override options file settings:
; --------------------------------------------------
;
; bias: BSM or OC or IM or OFF
;     im_threshold: (auto = 0.0)
;     im_pixrange: (default = 9.0)
; flux: I or IOF or OFF (Note: latter turns off absolute correction as
;       well, returns image DNs)
; /geom (turns on geometric correction)
; spec: text variable set to spectrum file for IOF mode 
; mask: text variable set to mask file for image mean 2hz noise
;       removal
; hotpix: Y or N (set to 'N' to turn off hot pixel removal, set to 'Y' to
;       turn on)
;
;===============================================================================

pro cisscal_cl,file,optionfile=optionfile,readlist=readlist,batchdir=batchdir,outputdir=outputdir,suffix=suffix,default=default,bias=bias,im_threshold=im_threshold,im_pixrange=im_pixrange,flux=flux,geom=geom,spec=spec,mask=mask,hotpix=hotpix

;INITIALIZATION:
;+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

@cisscal_common.pro

CisscalVers = '3.9'
IBatch = -1
DebugFlag = 1
Cisscal_Log,'Begin calibration...',FILENAME='stdout'

if !version.os_family eq 'windows' then slash = '\' else slash = '/' ; make work in windows

EnvVar = GETENV('CisscalDir')
IF EnvVar NE '' THEN CisscalDir = EnvVar
!PATH = !PATH + ':' + CisscalDir
IF STRMID(CisscalDir, STRLEN(CisscalDir)-1, 1) NE '/' THEN $
	CisscalDir = CisscalDir + slash

EnvVar = GETENV('CalibrationBaseDir')
IF EnvVar NE '' THEN CalibrationBaseDir = EnvVar
IF STRMID(CalibrationBaseDir, STRLEN(CalibrationBaseDir)-1, 1) NE '/' THEN $
	CalibrationBaseDir = CalibrationBaseDir + slash

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
             dark        : ptr_new({uselist : 0l, $
                                    dir     : '', $
                                    list    : '', $
                                    names   : ptr_new()})}

  BatchParams = ptr_new(params)

;+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

if n_elements(file) eq 0 then begin
	print,'ERROR: No input images specified.'
	return
endif

; set optionfile if necessary
if not keyword_set(optionfile) then begin
    if strmid(cisscaldir,strlen(cisscaldir)-1,1) ne slash then cisscaldir = cisscaldir + slash
    optionfile = cisscaldir + 'cisscal_default_options.txt'
endif

; add slash to batchdir string if necessary:
if keyword_set(batchdir) then begin
	if strmid(batchdir,strlen(batchdir)-1) ne slash then batchdir = batchdir + slash
endif else begin
	batchdir = ''
endelse

; add slash to outputdir string if necessary:
if keyword_set(outputdir) then begin
	if strmid(outputdir,strlen(outputdir)-1) ne slash then outputdir = outputdir + slash
endif else begin
	outputdir = ''
endelse

; get names (with path) of image files to be calibrated:
filelist = strsplit(file,',',/extract)

if strpos(file,slash,/reverse_search) eq -1 and not keyword_set(readlist) then $
	filelist = batchdir + filelist

; if list file specified, read in list of images:
if keyword_set(readlist) then begin
      if file_test(file,/read) then begin
          cisscal_readlist, file, filelist, nfiles, /noheader
          filelist = batchdir + filelist		
      endif else begin
            print, 'ERROR: Cannot run batch; no valid list file specified.'
            return
      endelse
endif else begin
     ; if '*' treat like a regular expression:
	if strpos(file,'*') ge 0 then begin 
           ; make filelist array:
            filelist = file_search(batchdir+file,count=nfiles,/test_regular)
            if nfiles eq 0 then begin ; file list appears to be invalid
                print,'ERROR: Cannot run batch; no image files found at requested location.'
                return
            endif
	endif
endelse

nimages = n_elements(filelist)

; get calibration options from file:
options = cisscal_readoptfile(optionfile,default=keyword_set(default),nimages=nimages,bias=bias,$
                              flux=flux,geom=geom,im_threshold=im_threshold,spec=spec,$
                              mask=mask,im_pixrange=im_pixrange,suffixes=suffixes,hotpix=hotpix)

for iim = 0l,nimages-1l do begin
    Cisscal_Log,''
    Cisscal_Log,'Now Processing Image #'+strtrim(iim+1,2)+' of '+strtrim(nimages,2)+'...' 

	; set calibration options
    if n_elements(options) gt 1 then CalOptions = ptr_new(options[iim]) else $
      CalOptions = ptr_new(options)

        ; default calibrated image suffix is .IMG.cal
    if not keyword_set(suffix) then begin
        if not keyword_set(default) and suffixes[iim] ne '' then $
          suffix = suffixes[iim] else $
          suffix = (*BatchParams).outputext
    endif

    imname = filelist[iim]

    IF OBJ_VALID(ImageObj) THEN OBJ_DESTROY,ImageObj

;	Return null object if the filename is blank
    ThisImageObj = OBJ_NEW()

;; if the file does not exist, do not try to open it.
;; continue to next file.
    IF NOT FILE_TEST(imname) THEN CONTINUE 
    
    ThisImageObj = OBJ_NEW('CassImg') 
    
    ThisImageObj->ReadVic, imname
    GuiImageName = imname
    
    ThisImageObj->RadiomCalib
    
    slashpos = strpos(filelist[iim],slash,/reverse_search)
    dotpos = strpos(filelist[iim],'.',/reverse_search)
    justfile = strmid(filelist[iim],slashpos+1,dotpos-(slashpos+1))
    
    savename = outputdir + justfile + suffix
    Cisscal_Log,'Saving to ',savename
    ThisImageObj->WriteVic,savename
endfor

IF OBJ_VALID(ThisImageObj) THEN OBJ_DESTROY,ThisImageObj

end
