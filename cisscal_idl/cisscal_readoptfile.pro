; CISSCAL Option file reader for GUI and command-line mode
;   Ben Knowles, 5/2006
;   - Update (BDK, 1/28/13): simplified bias/2hz removal options,
;     incorporated into GUI
;   - Update (BDK, 12/6/17): improved parsing code, fixed various anomalies
;   - Update (BDK, 6/20/18): Remove sens vs. time Vega-only option
;   - Update (BDK, 4/1/19): Change flux='OFF' to also turn off abs. correction

function cisscal_readoptfile,filename,default=default,nimages=nimages,bias=bias,flux=flux,geom=geom,im_threshold=im_threshold,im_pixrange=im_pixrange,spec=spec,mask=mask,suffixes=suffixes,bmode=bmode,hotpix=hotpix

nfiles = n_elements(filename)

; start by defining options array with default options:

optsarr = {                                                                 $
             lutc     :   ptr_new({onoff : 1L}),                            $  
             bitw     :   ptr_new({onoff : 1L}),                            $
             bias     :   ptr_new({onoff : 1L,                              $ 
                                   biasstripmean : 0L}),                    $
             twohz    :   ptr_new({onoff : 1L,                              $ 
                                   imagemean : ptr_new({onoff    : 0L,      $
                                                        maskfile  : '',     $
                                                        missingfile : '',   $
                                                        threshold : 0.0,    $
                                                        pixrange  : 9.0})}),$
             dark     :   ptr_new({onoff    : 1L,                           $
                                   darkfile : '',                           $
                                   hotpix   : 1L}),                         $
             abpp     :   ptr_new({onoff : 1L,                              $
                                   threshold : 30.0}),                      $
             lin      :   ptr_new({onoff : 1L}),                            $
             flat     :   ptr_new({onoff : 1L}),                            $
             flux     :   ptr_new({onoff : 1L,                              $
                                   ioverf : ptr_new({onoff    : 1L,         $
                                                     specfile : '',         $
                                                     dfs      : -1.0}),     $
                                   gain_onoff : 1L,                         $
                                   expt_onoff : 1L,                         $
                                   opta_onoff : 1L,                         $
                                   tran_onoff : 1L}),                       $
             corr     :   ptr_new({onoff : 1L,                              $
                                   time : 1L}),                             $
             geom     :   ptr_new({onoff : 0L}),                            $
             defval   :   ptr_new({saturated: !values.f_nan,                $
                                   missing:   !values.f_nan})}

if nfiles gt 1 then begin
    optsarr = replicate(optsarr,nfiles)
    suffixes = replicate('',nfiles)
endif else begin
    suffixes = ''
endelse

; Read option file (if /default keyword not set):

if not keyword_set(default) then begin
   for i=0,nfiles-1 do begin
      openr,lun,filename[i],/get_lun
        
      values = strarr(30)
      count = 0
      oneline = ''
      
      while not eof(lun) do begin
         readf, lun, oneline
         
;   Skip blank lines.
         if oneline eq '' then continue
            
;   Parse the line into fields separated by colons.
         split_line = strtrim(strsplit(oneline, ':', /extract),2)
         numfields = n_elements(split_line)
            
;   Interested in lines with two or more space-delimited fields.
         if split_line[0] eq '' then continue   ; skip blank line
         
         if numfields eq 1 then begin
            values[count] = ''                        ; if value field empty (no spaces)
         endif else begin
            if strpos(split_line[0],'suffix') ge 0 then values[count] = split_line[1L] else $ ;out suffix
               values[count] = strupcase(split_line[1l]) ; anything else
         endelse
            
         count = count + 1
      endwhile
        
      close,lun
      free_lun,lun
   
;   LUT conversion (Y or N)
      if values[0] eq 'Y' then (*(optsarr[i]).lutc).onoff = 1l else $
         (*(optsarr[i]).lutc).onoff = 0l
      
;   bitweight correction (Y or N)
      if values[1] eq 'Y' then (*(optsarr[i]).bitw).onoff = 1l else $
         (*(optsarr[i]).bitw).onoff = 0l
        
;   bias subtraction (Y or N)        
      if values[2] eq 'Y' then begin
         (*(optsarr[i]).bias).onoff = 1l

;   bias subtraction type (BSM or OC or IM)
         bmode = 1
         if values[3] eq 'BSM' then begin
            (*(optsarr[i]).bias).biasstripmean = 1l 
            (*(optsarr[i]).twohz).onoff = 0l
            bmode = 0
         endif else if values[3] eq 'OC' then begin
            (*(optsarr[i]).bias).biasstripmean = 0l 
            (*(optsarr[i]).twohz).onoff = 1l
            (*(*(optsarr[i]).twohz).imagemean).onoff = 0l
            bmode = 1
         endif else if values[3] eq 'IM' then begin
            (*(optsarr[i]).bias).biasstripmean = 1l
            (*(optsarr[i]).twohz).onoff = 1l
            (*(*(optsarr[i]).twohz).imagemean).onoff = 1l
            bmode = 2
         endif
         
      endif else begin
         (*(optsarr[i]).bias).onoff = 0l
         (*(optsarr[i]).twohz).onoff = 0l
      endelse
      
;      maskfile (auto if not set)     
      if values[4] ne '' then (*(*(optsarr[i]).twohz).imagemean).maskfile = values[4]

;      missingfile (not used)         
        
;      theshold (auto = 0.0)          
      val = float(values[6])
      (*(*(optsarr[i]).twohz).imagemean).threshold = val
        
;      pixrange (default = 9.0)       
      val = float(values[7])
      (*(*(optsarr[i]).twohz).imagemean).pixrange = val
        
;   dark subtraction (Y or N)        
      if values[8] eq 'Y' then (*(optsarr[i]).dark).onoff = 1l else $
         (*(optsarr[i]).dark).onoff = 0l
        
;   dark file (overrides models)   
      if values[9] ne '' then (*(optsarr[i]).dark).darkfile = values[9]

;   remove hot pixels (Y or N)  
      if values[10] eq 'Y' then (*(optsarr[i]).dark).hotpix = 1L else $
         (*(optsarr[i]).dark).hotpix = 0L
      
;   anti-blooming pixel pair removal 
      if values[11] eq 'Y' then (*(optsarr[i]).abpp).onoff = 1l else $
         (*(optsarr[i]).abpp).onoff = 0l
        
;   abpp threshold (default = 30.0)
      val = float(values[12])
      (*(optsarr[i]).abpp).threshold = val
        
;   linearize (Y or N)
      if values[13] eq 'Y' then (*(optsarr[i]).lin).onoff = 1l else $
         (*(optsarr[i]).lin).onoff = 0l
        
;   flatfield (Y or N)   
      if values[14] eq 'Y' then (*(optsarr[i]).flat).onoff = 1l else $
         (*(optsarr[i]).flat).onoff = 0l
        
;   flux conversion (Y or N)
      if values[15] eq 'Y' then (*(optsarr[i]).flux).onoff = 1l else $
         (*(optsarr[i]).flux).onoff = 0l
        
;   flux conversion type (I or IOF)
      if values[16] eq 'IOF' then (*(*(optsarr[i]).flux).ioverf).onoff = 1l else if $
         values[16] eq 'I' then (*(*(optsarr[i]).flux).ioverf).onoff = 0l
        
;      spectrum file (overrides solar)
      if values[17] ne '' then (*(*(optsarr[i]).flux).ioverf).specfile = values[17]
        
;      distance from sun (J, S, or AU)
      if values[18] eq 'J' then (*(*(optsarr[i]).flux).ioverf).dfs = -2L else if $
         values[18] eq 'S' then (*(*(optsarr[i]).flux).ioverf).dfs = -1L
        
      if stregex(values[18],'[0123456789]',/boolean) then $
         (*(*(optsarr[i]).flux).ioverf).dfs = float(values[18])
        
;      multiply by gain (Y or N)
      if values[19] eq 'Y' then (*(optsarr[i]).flux).gain_onoff = 1L else $
         (*(optsarr[i]).flux).gain_onoff = 0L

;      divide by exposure time (Y or N)
      if values[20] eq 'Y' then (*(optsarr[i]).flux).expt_onoff = 1L else $
         (*(optsarr[i]).flux).expt_onoff = 0L

;      divide by optics area/pixel solid angle (Y or N)
      if values[21] eq 'Y' then (*(optsarr[i]).flux).opta_onoff = 1L else $
         (*(optsarr[i]).flux).opta_onoff = 0L

;      divide by system transmission (Y or N)
      if values[22] eq 'Y' then (*(optsarr[i]).flux).tran_onoff = 1L else $
         (*(optsarr[i]).flux).tran_onoff = 0L

;   absolute flux correction (aka correction factors) (Y or N)    
      if values[23] eq 'Y' then (*(optsarr[i]).corr).onoff = 1l else (*(optsarr[i]).corr).onoff = 0l

;   sensitivity vs. time correction (Y or N)
      if values[24] eq 'Y' then (*(optsarr[i]).corr).time = 1l else (*(optsarr[i]).corr).time = 0l
      
;   geometric correction (Y or N)    
      if values[25] eq 'Y' then (*(optsarr[i]).geom).onoff = 1l else $
         (*(optsarr[i]).geom).onoff = 0l
      
;   default output filename suffix
      if values[26] ne '' then suffixes[i] = values[26]
  
;   default output saturated pixel value
      if (values[27] eq '' or values[27] eq 'NULL') then $
         (*(optsarr[i]).defval).saturated = !values.f_infinity else if $                  ; no change
         values[27] eq 'NAN' then (*(optsarr[i]).defval).saturated = !values.f_nan else $      ; NAN
            (*(optsarr[i]).defval).saturated = float(values[27])

;   default output missing pixel value
      if values[28] eq '' then (*(optsarr[i]).defval).missing = 0.0 else if $
         values[28] eq 'NAN' then (*(optsarr[i]).defval).missing = !values.f_nan else $ ; NAN
            (*(optsarr[i]).defval).missing = float(values[28])
   endfor 
endif

for i=0,nfiles-1 do begin
;Keyword calibration options override option file settings and defaults:
    if keyword_set(bias) then begin
       if bias eq 'BSM' then begin
          bmode = 0
          (*(optsarr[i]).bias).onoff = 1l
          (*(optsarr[i]).bias).biasstripmean = 1l
          (*(optsarr[i]).twohz).onoff = 0l
       endif else if bias eq 'OC' then begin
          bmode = 1
          (*(optsarr[i]).bias).onoff = 1l
          (*(optsarr[i]).bias).biasstripmean = 0l
          (*(optsarr[i]).twohz).onoff = 1l
          (*(*(optsarr[i]).twohz).imagemean).onoff = 0l
       endif else if bias eq 'IM' then begin
          bmode = 2
          (*(optsarr[i]).bias).onoff = 1l
          (*(optsarr[i]).bias).biasstripmean = 1l
          (*(optsarr[i]).twohz).onoff = 1l
          (*(*(optsarr[i]).twohz).imagemean).onoff = 1l
       endif else if bias eq 'OFF' then begin
          (*(optsarr[i]).bias).onoff = 0l
          (*(optsarr[i]).twohz).onoff = 0l
       endif
    endif

    if keyword_set(im_threshold) then $
         (*(*(optsarr[i]).twohz).imagemean).threshold = im_threshold

    if keyword_set(im_pixrange) then $
         (*(*(optsarr[i]).twohz).imagemean).pixrange = im_pixrange

    if keyword_set(geom) then (*(optsarr[i]).geom).onoff = 1l

    if keyword_set(flux) then begin
       if flux eq 'I' then begin
          (*(optsarr[i]).flux).onoff = 1l
          (*(*(optsarr[i]).flux).ioverf).onoff = 0l
       endif else if flux eq 'IOF' then begin
          (*(optsarr[i]).flux).onoff = 1l
          (*(*(optsarr[i]).flux).ioverf).onoff = 1l
       endif else if flux eq 'OFF' then begin
          (*(optsarr[i]).flux).onoff = 0l
          (*(optsarr[i]).corr).onoff = 0l          
       endif
    endif 

    if keyword_set(spec) then begin
        (*(optsarr[i]).flux).onoff = 1l
        (*(*(optsarr[i]).flux).ioverf).onoff = 1l
        (*(*(optsarr[i]).flux).ioverf).specfile = spec        
    endif

    if keyword_set(mask) then begin
        (*(optsarr[i]).twohz).onoff = 1l
        (*(*(optsarr[i]).twohz).imagemean).onoff = 1l
        (*(*(optsarr[i]).twohz).imagemean).maskfile = mask
    endif

    if keyword_set(hotpix) then begin
       hotpixval = -1
       if hotpix eq 'Y' then hotpixval = 1 else $
          if hotpix eq 'N' then hotpixval = 0
       if hotpixval ge 0 then (*(optsarr[i]).dark).hotpix = long(hotpixval)
    endif
    
endfor

return,optsarr

end

