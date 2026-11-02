; CISSCAL Batch mode GUI event handler
; - Ben Knowles, 5/2004

PRO batchgui_event, event
@cisscal_common.pro

; Gain access to the batch GUI's control structure:
widget_control, event.top, get_uvalue=pstruct, /no_copy

; Get ImgObj from uvalue of dummy top-level base:
stash = widget_info(event.top, /child)
widget_control, stash, get_uvalue=dummytlb
widget_control, dummytlb, get_uvalue=ImgObj, /no_copy

CASE event.id OF
    pstruct.cancelid   : BEGIN     ; CANCEL
        widget_control, dummytlb, set_uvalue=ImgObj, /no_copy
        widget_control, event.top, set_uvalue=pstruct, /no_copy
        widget_control, event.top, /destroy
        return
        END

    pstruct.runbatchid : BEGIN  ; RUN BATCH MODE
       ; set input/output directories
        widget_control, pstruct.indirid, get_value=temp
        widget_control, pstruct.indirid, set_value=strtrim(temp,2)
        (*BatchParams).inputdir = strtrim(temp,2)

        widget_control, pstruct.instring, get_value=temp
        widget_control, pstruct.instring, set_value=strtrim(temp,2)
        if (*BatchParams).inputtype eq 0 then $
           (*BatchParams).inputregexp = strtrim(temp,2) else $
              (*BatchParams).inputlist = strtrim(temp,2)
        
        widget_control, pstruct.outdirid, get_value=temp
        widget_control, pstruct.outdirid, set_value=strtrim(temp,2)
        (*BatchParams).outputdir = strtrim(temp,2)       

        widget_control, pstruct.outextid, get_value=temp
        widget_control, pstruct.outextid, set_value=strtrim(temp,2)
        (*BatchParams).outputext = strtrim(temp,2)

        if (*(*BatchParams).dark).uselist then begin
           widget_control, pstruct.darkdirid, get_value=temp
           (*(*BatchParams).dark).dir = strtrim(temp,2)

           widget_control, pstruct.darklistid, get_value=temp
           (*(*BatchParams).dark).list = strtrim(temp,2)
        endif

        if strlowcase(!version.os_family) eq 'windows' then $     ; make work in windows
          slash = '\' else slash = '/'

        inputdir = (*BatchParams).inputdir
        if strmid(inputdir, strlen(inputdir)-1, 1) ne slash then $
          inputdir = inputdir + slash
       
        outputdir = (*BatchParams).outputdir
        if strmid(outputdir, strlen(outputdir)-1, 1) ne slash then $
          outputdir = outputdir + slash

       ; kill window:
        GuiEnabMenuOpts,0
        widget_control, dummytlb, set_uvalue=ImgObj, /no_copy
        widget_control, event.top, set_uvalue=pstruct, /no_copy
        widget_control, event.top, /destroy
        
        if (*BatchParams).inputtype eq 0 then begin   ; if using filter
            
                                ; make filelist array:
            filelist = file_search(inputdir+(*BatchParams).inputregexp,$
                                   count=nfiles,/test_regular)
            
            if nfiles eq 0 then begin ; file list appears to be invalid
                if DebugFlag gt 0 then Cisscal_Log,$
                  '  ERROR: Cannot run batch; no image files found at requested location.'
                return
            endif
    
        endif else begin                              ; if using input list
            inputlist = (*BatchParams).inputlist
           ; if no directory specified, assume list in input directory
            if strpos(inputlist,slash,/reverse_search) eq -1 then $
              inputlist = inputdir + inputlist

            if file_test(inputlist,/read) then begin
                
                cisscal_readlist, inputlist, filelist, nfiles, /noheader
                filelist = strtrim(inputdir + filelist,2)

            endif else begin
                if DebugFlag gt 0 then Cisscal_Log,$
                  '  ERROR: Cannot run batch; no valid file list specified.'
                return
            endelse
        endelse
             
       ; if reading dark files from list, read list into names array:
        if (*(*BatchParams).dark).uselist then begin
            darklistfile = (*(*BatchParams).dark).list
            darkdir = (*(*BatchParams).dark).dir
            if strmid(darkdir, strlen(darkdir)-1, 1) ne slash then $
              darkdir = darkdir + slash
            if strpos(darklistfile,slash) eq -1 then $ ;full path not given
              darklistfile = darkdir + darklistfile ; assume file is in darkdir

            if file_test(darklistfile,/read) then begin
                cisscal_readlist, darklistfile, darklist, ndfiles, /noheader
                if ndfiles eq nfiles then begin
                    darklist = darkdir + strtrim(darklist,2)
                    if ptr_valid((*(*BatchParams).dark).names) then $
                      ptr_free,(*(*BatchParams).dark).names
                    (*(*BatchParams).dark).names = ptr_new(darklist) 
                endif else begin
                    if DebugFlag gt 0 then Cisscal_Log,$
                      '  ERROR: Cannot run batch; dark list file is invalid.'
                    return
                endelse
            endif else begin
                if DebugFlag gt 0 then Cisscal_Log,$
                  '  ERROR: Cannot run batch; dark list file not found.'
                return
            endelse
        endif    

        if DebugFlag gt 0 then begin
           Cisscal_Log
           Cisscal_Log,'Begin batch processing...'
        endif
        
        WIDGET_CONTROL, /HOURGLASS ; time-intensive...
        for IBatch = 0l, nfiles-1l do begin         
           if DebugFlag gt 0 then begin
              Cisscal_Log
              Cisscal_Log,'****************************************************'          
              Cisscal_Log,'  Now processing image '+ filelist[IBatch]
              Cisscal_Log,'   Image #'+strtrim(IBatch+1,2)+' of '+$
                          strtrim(nfiles,2)
              Cisscal_Log,'****************************************************'          
           endif
           NewImgObj = GuiOpenFile(ImgObj,filename=filelist[IBatch])
           if OBJ_VALID(NewImgObj) then begin
              GuiEnabMenuOpts,1
              NewImgObj->RadiomCalib,CancelFlag=CancelFlag
                
              slashpos = strpos(filelist[IBatch],slash,/reverse_search)
              dotpos = strpos(filelist[IBatch],'.')
              justfile = strmid(filelist[IBatch],slashpos+1,dotpos-(slashpos+1))

              if CancelFlag eq 2 then break
              if CancelFlag eq 0 then $
                 GuiSaveFile, NewImgObj, filename=outputdir + justfile + $
                              (*BatchParams).outputext
           endif else begin
              GuiEnabMenuOpts,0
           endelse
        endfor
        IBatch = -1             ; get out of batch mode
 
        return
        END

    pstruct.indirid   : BEGIN
        widget_control, pstruct.indirid, get_value=temp

        widget_control, pstruct.outdirin, get_value=temp2
        if temp2 then begin
           widget_control, pstruct.outdirid, set_value=temp
        endif
        END

    pstruct.inputtype : BEGIN
        widget_control, pstruct.inputtype, get_value=temp
        (*BatchParams).inputtype = temp
        if (*BatchParams).inputtype eq 0 then $
          widget_control, pstruct.instring, set_value=(*BatchParams).inputregexp else $
          widget_control, pstruct.instring, set_value=(*BatchParams).inputlist
        END

    pstruct.instring   : BEGIN
        widget_control, pstruct.instring, get_value=temp

        if (*BatchParams).inputtype eq 0 then $
          (*BatchParams).inputregexp = temp else $
          (*BatchParams).inputlist = temp
        END

    pstruct.indirbut  : BEGIN
        widget_control, pstruct.indirid, get_value=temp
        indir = dialog_pickfile(/directory,path=temp)
        
        if file_test(indir,/dir) then begin 
            widget_control, pstruct.indirid, set_value=indir
            widget_control, pstruct.outdirin, get_value=temp2
            if temp2 then begin
               widget_control, pstruct.outdirid, set_value=indir
            endif   
        endif
        END

    pstruct.outdirin  : BEGIN
        widget_control, pstruct.outdirin, get_value=temp
        (*BatchParams).outdirin = temp
        widget_control, pstruct.indirid, get_value=temp2

        if temp then begin
           widget_control, pstruct.outdirid, set_value=temp2
           widget_control, pstruct.outdirbase, sensitive = 0
        endif else begin
           widget_control, pstruct.outdirbase, sensitive = 1
        endelse
        END

    pstruct.outdirbut  : BEGIN
        widget_control, pstruct.indirid, get_value=temp
        outdir = dialog_pickfile(/directory,path=temp)

        if file_test(outdir,/dir) then begin
            widget_control, pstruct.outdirid, set_value=outdir
        endif
        END

    pstruct.darkoptsid : BEGIN
        widget_control, pstruct.darkoptsid, get_value=temp

        if temp eq 0 then begin 
            (*(*CalOptions).dark).darkfile = ''
            (*(*BatchParams).dark).uselist = 0
            widget_control,pstruct.darkbaseid,sensitive=0
        endif else if temp eq 1 then begin
            (*(*BatchParams).dark).uselist = 1
            widget_control,pstruct.darkbaseid,sensitive=1
        endif
        END

    ELSE: BEGIN
        END

ENDCASE

widget_control, dummytlb, set_uvalue=ImgObj, /no_copy
widget_control, event.top, set_uvalue=pstruct, /no_copy

END



;;	PRO GuiBatch
;;	 Set batch mode options, launch batch processing

PRO cisscal_batchgui, ImgObj, ev
@cisscal_common.pro

 ; main widget base:
  tlb = widget_base(title='Set Batch Options', /column,$
                  group_leader=ev.top, /floating, mbar=MenuBar)

 ; Create dummy top level base widget to hold direct reference to 
 ; ImgObj; widget ID will be placed into first child widget of
 ; the main top level base:  
  dummytlb = widget_base()

 ;******************
 ; construct widget:
 ;******************

;  toplab = widget_label(tlb,value='Press return after each entry.',$
;                        /align_center)

 ; set default path if no path has already been specified:
  if (*BatchParams).inputdir eq '' then begin
      ImPathSz = SIZE(ImPath)
      IF ( ImPathSz[ImPathSz[0]+1] NE 7 ) THEN BEGIN ; if not a string
          ImPath = ImageBaseDir
      ENDIF

      (*BatchParams).inputdir = ImageBaseDir
      (*BatchParams).outputdir = ImageBaseDir
  endif

 ; editable text: 
  indirval = (*BatchParams).inputdir
  indirlab = widget_label(tlb,value='Input Directory:',/align_left)
  indirbase = widget_base(tlb,/row)
  indirid = widget_text(indirbase,value=indirval,/edit,xsize=58,/all_events)
  indirbut = widget_button(indirbase,value='Browse...')

  inputbase = widget_base(tlb,/row)
  inputlab = widget_label(inputbase,value='Use:',/align_left)
  inputtype = cw_bgroup(inputbase,['Input filter','Input file list'],$
                       /exclusive,/no_release,/row,set_value=(*BatchParams).inputtype)
  inregval = (*BatchParams).inputregexp
  inlistval = (*BatchParams).inputlist

  if (*BatchParams).inputtype eq 0 then ival = inregval else ival = inlistval
  instring = widget_text(tlb,value=ival,/edit,/all_events)
  
  outdirval = (*BatchParams).outputdir
  outdirlab = widget_label(tlb,value='Output Directory:',/align_left)
  outdirbase = widget_base(tlb,/row,sensitive = (*BatchParams).outdirin eq 0)
  outdirid = widget_text(outdirbase,value=outdirval,/edit,xsize=58,/all_events)
  outdirbut = widget_button(outdirbase,value='Browse...')

  outdirin = cw_bgroup(tlb,'Set output dir same as input',set_value=(*BatchParams).outdirin,$
                       /nonexclusive,xpad=20) 

  outextval = (*BatchParams).outputext
  outextlab = widget_label(tlb,value='Output Filename Extension:',/align_left)
  outextid = widget_text(tlb,value=outextval,/edit,/all_events)

 ; dark subtraction options:

  if (*(*BatchParams).dark).uselist eq 1 then begin
      darkoptsval = 1
      darkfilesens = 1
  endif else begin
      darkoptsval = 0
      darkfilesens = 0
  endelse

  darkoptslab = widget_label(tlb,value='Dark Subtraction Options:',/align_left)

  darkoptsid = cw_bgroup(tlb,['Interpolation model',$
                       'Choose Dark List'], set_value=darkoptsval, /no_release, $
                        /exclusive, /column)

  darkbaseid = widget_base(tlb,/column,sensitive=darkfilesens)

  darkdirlab = widget_label(darkbaseid,value='Specify directory containing darks:',$
                            /align_left)
  darkdirval = (*(*BatchParams).dark).dir
  darkdirid = widget_text(darkbaseid, value=darkdirval, /edit,/all_events)

  darklistlab = widget_label(darkbaseid,value=$
           'Specify dark list (assumed to be in dark dir unless full path is given):',$
           /align_left)
  darklistval = (*(*BatchParams).dark).list
  darklistid = widget_text(darkbaseid, value=darklistval, /edit,/all_events)

 ; buttons:
  btnbase = widget_base(tlb,/row)

  cancelid = widget_button(btnbase,value = 'Cancel')
  runbatchid = widget_button(btnbase,value = 'Run batch')

 ; make structure to hold widget IDs:
  pstruct = {indirid    : indirid,$
             instring   : instring,$
             inputtype  : inputtype,$
             indirbut   : indirbut,$
             outdirid   : outdirid,$
             outextid   : outextid,$
             outdirbut  : outdirbut,$
             outdirbase : outdirbase,$
             outdirin   : outdirin,$
             darkoptsid : darkoptsid,$
             darkbaseid : darkbaseid,$
             darkdirid  : darkdirid,$
             darklistid : darklistid,$
             cancelid   : cancelid,$
             runbatchid : runbatchid}

  widget_control, tlb, /realize
  widget_control, tlb, set_uvalue=pstruct, /no_copy

  widget_control, dummytlb, set_uvalue=ImgObj, /no_copy

  stash = widget_info(tlb, /child)
  widget_control, stash, set_uvalue=dummytlb

  xmanager, 'batchgui', tlb

; Retrieve the reference to the ImgObj, so that it will be 
; associated again with the incoming argument:
  widget_control, dummytlb, get_uvalue=ImgObj, /no_copy

; Release the dummy top-level base:
  widget_control, dummytlb, /destroy

  widget_control, ev.top, set_uvalue=ImgObj, /no_copy

END
