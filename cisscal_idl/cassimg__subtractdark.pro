;;	cassimg__subtractdark.pro
;;
;;	Subtract a darkcurrent image from the working image
;;	Kevin Beurle	January 1999
;;
;;      Revisions by Ben Knowles:
;;         - new dark simulation algorithm from Bob West (2002 and 2004)
;;         - added summed images; faster algorithm from Daren Wilson
;;           (2005)
;;         - removed 2-parameter model (2008)
;;         - added mid frequency filtering (Jan 2013)
;;         - added "hot pixels" (Feb 2013)
;;           - pixels identified as having erroneously high dark
;;             current at a given time/epoch

;-----------------------------
; create darkfile name string:
;-----------------------------
function darkfilename,sum, exp, conv, comp, btsm, cdsr, ratio, roindex, camera, roo, subscript, fsw 
@cisscal_common.pro	; include COMMON definitions

  darkdir = CalibrationBaseDir + 'darkcurrent/'

  sums = ['FULL','SUM2','SUM4']
  sumstr = string(where(sums eq sum),format='(I1)')

  exps=[0L,5L,10L,15L,20L,25L,30L,35L,40L,50L,60L,70L,80L,90L,100L,120L,150L,180L,220L,$
        260L,320L,380L,460L,560L,680L,820L,1000L,1200L,1500L,1800L,2000L,2600L,3200L,3800L,$
        4600L,5600L,6800L,8200L,10000L,12000L,15000L,18000L,22000L,26000L,32000L,38000L,$
        46000L,56000L,68000L,82000L,100000L,120000L,150000L,180000L,220000L,260000L,320000L,$
        380000L,460000L,560000L,680000L,1000000L,1200000L,-999L]
  expind = (where(exps eq long(exp*1000.)))[0]
  if expind lt 10 then expstr = '0' + string(expind,format='(I1)') else $
    expstr = string(expind,format='(I2)')

  convs = ['12BIT','TABLE','8LSB']
  convstr = string(where(convs eq conv),format='(I1)')

  comps = ['NOTCOMP','LOSSLESS','LOSSY']
  compstr = string(where(comps eq comp),format='(I1)')

  btsmstr = string(btsm,format='(I1)')

  if cdsr lt 10 then cdsrstr = '0' + string(cdsr,format='(i1)') else $
    cdsrstr = string(cdsr,format='(i2)')
  
  rind = fix(20.0*alog(ratio < 10.0)/alog(10.0))
  if rind lt 10 then ratiostr = '0' + string(rind,format='(I1)') else $
    ratiostr = string(rind,format='(I2)')

  if roindex lt 10 then roindstr = '0' + string(roindex,format='(I1)') else $
    roindstr = string(roindex,format='(I2)')

  roostr = string(roo,format='(I1)')
  
  if fsw ge 1.4 then fswstr = strtrim(string(fix(round(10.*(fsw-1.)))),2) else fswstr = ''
  
  if subscript ne '' then begin
     return,strlowcase(strmid(camera,0,1))+'_dark_'+sumstr+expstr+convstr+compstr+$
            btsmstr+cdsrstr+ratiostr+roindstr+roostr+fswstr+'_'+subscript+'.img'   
  endif else begin
     return,strlowcase(strmid(camera,0,1))+'_dark_'+sumstr+expstr+convstr+compstr+$
            btsmstr+cdsrstr+ratiostr+roindstr+roostr+fswstr+'.img'   
  endelse


end

;-----------------------------------------------------
; call linetime to get start, end and duration arrays:
;-----------------------------------------------------
pro get_line_times, sum, exp, conv, comp, btsm, cdsr, ratio, roindex, camera, roo, start_time, end_time, duration, fsw

  case sum of
      'FULL': numlines = 1024
      'SUM2': numlines = 512
      'SUM4': numlines = 256
  endcase
  
  time_to_read = fltarr(numlines)
  
  for lline = 0,numlines-1 do begin
      time = cisscal_linetime(sum, exp, conv, comp, btsm, cdsr, lline+1, $
                ratio=ratio, rdind=roindex, camera=camera, roo=roo, fsw=fsw)
      time_to_read(lline) = time
  endfor

; deal with bug in linetime code:
  negtime = where(time_to_read lt 0,nnt)
  if nnt gt 0 then return
  
  for i = 0,numlines-1 do begin
      for j = 0,i do end_time(i,j) = time_to_read(i-j)   
      for j = 0,i do begin
          if j lt i then start_time(i,j) = end_time(i,j+1) else $
                         start_time(i,j) = 0.0
          duration(i,j) = end_time(i,j)-start_time(i,j)
      endfor
  endfor
  
  duration(*,*) = duration(*,*) > 0.0
  end_time(*,*) = start_time(*,*) + duration(*,*)

end

;--------------------------------------------------------------
; actually create dark array from parameters and linetime info:
;--------------------------------------------------------------
pro make_manyline_dark, params, start_time, end_time, duration, dark

;; Compute one line of a synthetic dark frame from timing tables
;;    and dark current parameters for each pixel
;;
;; INPUTS:
;;  params: Dark parameter array(1024,8)
;     Parameters for dark current for each pixel. The second
;     dimension is the parameter 
;
;     [Constant, linear, A_1,tau_1,A_2,tau_2,A_3,tau_3]
; 
;     Where darkcurrent = Constant+linear*t+sum((1.0-a_i exp(-t/tau_i)))
;
;;  start_time and end_time:   
;     Arrays 1024X1024 telling the start and end times when a
;     potential well starting on line i reaches and exits line j
;
;;  Optional input: firstline, lastline  
;     only compute the dark(firstline:lastline)
;
;; OUTPUT: darkline contains calculated dark current (electrons)

  tgrid = [0.,10.,32.,100.,220.,320.,460.,1200.]

  s = size(start_time)
  numlines = s(2)
  sparams = size(params)
  numsamps = sparams(1)
  num_params = sparams(3)
  v1 = fltarr(num_params,num_params)
  for j = 0,num_params-1 do v1(j,j) = 1.0

; THE FOLLOWING CODE HAS BEEN REPLACED BY A FASTER VERSION, BELOW:
;   - BK, 6/23/05, changes by Daren Wilson

;   c1 = fltarr(num_params,numlines,numlines)
;   dark = fltarr(numsamps,numlines)
;   temp = dark
;
;   for jline = line1, line2 do begin
;       temp[0:numsamps-1] = params[0:numsamps-1,jline,0] ; constant term
;      ; sum the contribution from every pixel downstream of jline, including jline
;       for kline = 0,jline do begin  
;         ; derive coefficients so that parameters can be multiplied and added
;         ; rather than interpolated
;           for j = 0,num_params-1 do c1[j,jline,kline] = $
;             interpol(reform(v1[j,*]),tgrid,end_time[jline,kline],/spline) - $
;             interpol(reform(v1[j,*]),tgrid,start_time[jline,kline],/spline)
;          
;           z = where(c1[*,jline,kline] ne 0.0, nz)
;
;           for j = 0,n_elements(z)-1 do temp[0:numsamps-1] = temp[0:numsamps-1] + $
;             params[0:numsamps-1,kline,z[j]]*c1[z[j],jline,kline]
;       endfor
;       dark[0:numsamps-1,jline] = temp[0:numsamps-1]
;   endfor

  dark = fltarr(numsamps,numlines)
  temp = fltarr(numsamps)
  
  for jline = 0, numlines-1 do begin
      temp = params[*,jline,0] ; constant term
     ; sum the contribution from every pixel downstream of jline, including jline
      for kline = 0,jline do begin  
        ; derive coefficients so that parameters can be multiplied and added
        ; rather than interpolated
          timespan = [start_time[jline,kline], end_time[jline,kline]]
          for j = 0,num_params-1 do begin
             c = interpol(reform(v1[j,*]), tgrid, timespan,/spline) 
             c = c[1] - c[0]  
             if c ne 0.0 then temp = temporary(temp + c*params[*,kline,j]) 
          endfor
  
      endfor
      dark[*,jline] = temp
  endfor

end

;------------------------------------------
; wrapper routine used to create new darks:
;------------------------------------------
function makedarkarray, sum, exp, conv, comp, btsm, cdsr, ratio, roindex, camera, roo, dparamfile, hotfile, fsw

@cisscal_common.pro	; include COMMON definitions

  dparampath = CalibrationBaseDir + 'darkcurrent/' + dparamfile

  sums = ['FULL','SUM2','SUM4']
  lines = [1024,512,256]
  numlines = lines[(where(sums eq sum))[0]]

  numsamps = numlines
  lastline = numlines-1
  
  start_time = fltarr(numsamps,numlines)
  end_time = start_time
  duration = start_time

  get_line_times, sum, exp, conv, comp, btsm, cdsr, $
                 ratio, roindex, camera, roo, start_time, end_time, duration, fsw

 ; deal with bug in linetime:
  good = where(start_time ne end_time,ngood)

  if ngood ne 0 then begin

    ; read dark parameter file
     tgrid = [0.,10.,32.,100.,220.,320.,460.,1200.]
     params = fltarr(1024,1024,8)
     openr,params_lun,dparampath,/get_lun,/xdr
     readu,params_lun,params
     close,params_lun
     free_lun,params_lun

; Apply hot pixel correction:
     if hotfile ne '' then begin
    ; read hot pixel file...
        Cisscal_Log,'    Opening hot pixel file: ',hotfile
        openr,hotfilelun,hotfile,error=err,/get_lun
        
        if (err eq 0) then begin
           while not eof(hotfilelun) do begin
              text=''
              readf, hotfilelun, text
              if strpos(text, '\begindata') ge 0 then break
           endwhile
           text=''        
           readf,hotfilelun,text ; second line gives exposure times (s)
           text = strtrim(strcompress(text),1)
           
           fields = strsplit(text,' ',/extract)
           if fields[0] ne '' then $
              exptimes = float(fields[2:n_elements(fields)-1])
           
           readf,hotfilelun,text ; third line gives gain state
           text = strtrim(strcompress(text),1)
           
           fields = strsplit(text,' ',/extract)
           if fields[0] ne '' then $
              gains = float(fields[2:n_elements(fields)-1])
           
           count = 1
           while not eof(hotfilelun) do begin ; rest of file contains data
              readf,hotfilelun,text
              text = strtrim(strcompress(text),1)
              fields = strsplit(text,' ',/extract)
              if fields[0] ne '' then begin
                 if count eq 1 then begin
                    x = fix(fields[0])
                    y = fix(fields[1])
                    hotsat = fix(fields[n_elements(fields)-1])
                    elec = float(fields[2:n_elements(fields)-2]) 
                 endif else begin
                    x = [x,fix(fields[0])]
                    y = [y,fix(fields[1])]
                    hotsat = [hotsat,fix(fields[n_elements(fields)-1])]
                    elec = [[elec],[float(fields[2:n_elements(fields)-2])]]
                 endelse
              endif
              count = count + 1
           endwhile
           
        endif
        close,hotfilelun
        free_lun,hotfilelun

        elec = transpose(elec)
        npix = n_elements(x)

    ; loop through hot pixels and update dark parameter array
        for i=0l,npix-1l do begin
           hotdata = elec[i,*]

           if hotsat[i] ne 0 then begin
              
              if hotsat[i] gt 0 then maxexp = exptimes[hotsat[i]-1]
              if hotsat[i] lt 0 then maxexp = max(exptimes)
              
              newexptimes = exptimes
              
          ; use interpol to get value for
          ; highest overlapping exposure index

              good = where(newexptimes le maxexp,ngood) ; interpol using only non-saturated data
              
              if ngood gt 1 then params[x[i],y[i],*] = $
                 interpol(hotdata[good],newexptimes[good],tgrid) else $
                    Cisscal_Log,'     Uncorrected hot pixel:',x[i],y[i]

           endif
        endfor   
     endif

; Assume WAC dark current is 0 for 0.005 ms. This is not the case for
; the NAC where there are negative values near the left edge of the frame:
     if camera eq 'WAC' then params[*,*,0] = 0.0

                                ; Following case statement written by
                                ; Bob West and added by BK (4/19/05) to
                                ; add functionality for summed images:
     numpix = 1024/numlines
     case numlines of
          1024: make_manyline_dark, params, start_time, end_time, duration, dark_e
          else: begin
              summed_params = fltarr(numlines,numlines,8)
                                ; sum coefficients
              for k = 0,7 do begin
                  for j = 0,numlines-1 do begin
                      for i = 0,numlines-1 do begin
                          summed_params(i,j,k) = $
                            total(params[numpix*i:numpix*(i+1)-1,numpix*j:numpix*(j+1)-1,k])
                      endfor
                  endfor
              endfor
              make_manyline_dark, summed_params, start_time, end_time, duration, dark_e    
          end
      endcase

; Median-ed dark images have some spikes below the fitted curve.
; These are probably artifacts and the next section removes them.

      di1 = fltarr(numlines,numlines)
      for i = 0,numlines-1 do di1[i,*] = median(reform(dark_e[i,*]),5)
      z = where(di1 - dark_e gt 10,nz)
      if nz gt 0 then dark_e[z] = di1[z]

      return,dark_e
      
   endif else begin             ; if bug in linetime
      
      return,fltarr(numsamps,numlines)
      
   endelse

end


PRO CassImg::SubtractDark

;	Algorithm to subtract spatial darkcurrent structure and RBI (Residual Bulk Image)
;
;	Update: As of mid-2000, the darkcharge subtraction is done using
;	 a synthetic dark image from a mathematical darkcharge model.
;	The DarkFName parameter is therefore not currently in use but
;	 is left there for possible future changes to the algorithm.
;
;	Update #2: Code changed in 4/02 by Ben Knowles to allow for one of 
;	 three dark subtraction methods: a 2-parameter model (default; already
;	 implemented), an interpolation model (not yet fully implemented), or 
;	 simply subtracting out a pre-made dark image of one's choice. The 
;	 filename of the latter is selected within the GUI and is now 
;	 contained in DarkFName. 
;
;       Update #3: Interpolation model improved in 2004 and 2005
; 
;       Update #4: 2-parameter model removed in 2008
;
;       Update #5: Mid-frequency filtering added in January 2013
;
;       Update #6: Hot pixel implementation finalized in August 2013

@cisscal_common.pro	; include COMMON definitions

IF DebugFlag GT 0 THEN BEGIN
   CISSCAL_Log,'Subtracting dark:'
ENDIF

dparamfile = ''

gainstate = self.GainState ;0,1,2,3
camera = self.Instrument   ;issna, isswa
conv = self.ConvType       ;table,12-bit,8lsb
mode = self.ShutModID      ;naconly, waconly, botsim
comp = self.EncType        ;lossless,lossy,notcomp
sum = self.InstModID       ;full,sum2,sum4
time = self.ExpDur
fsw = float(self.Fsw)      ;1.3, 1.4, etc. 

dohot = (*(*CalOptions).dark).hotpix    ; remove hot pixels?

exp = time/1000.         

if conv eq '8LSB' then DNSatPoint = 255.0 else dnsatpoint = 4095.0

; USER-SPECIFIED DARK FILE:

if (IBatch lt 0 and (*(*CalOptions).dark).darkfile ne '') or $      ;not batch
   (IBatch ge 0 and (*(*BatchParams).dark).uselist ne 0) then begin ;batch
   
; if in batch mode:
   if IBatch ge 0 then begin
      darklist = *(*(*BatchParams).dark).names
      DarkFName = darklist[IBatch]
   endif else begin
      DarkFName = (*(*CalOptions).dark).darkfile
   endelse

   if file_test(DarkFName) then begin

      DarkObj = OBJ_NEW('CassImg') 
        
      DarkObj->ReadVic, DarkFName, /Quiet, /NotCass
      dark_DN=DarkObj->Image()
      
      OBJ_DESTROY, DarkObj	; Finished with object: reclaim the space
        
     ; correct for summation

      IF (sum EQ 'SUM2') AND ((size(dark_DN))[1] ne 512) THEN $
         dark_DN =  4 * REBIN(dark_DN, 512, 512)
      IF (sum EQ 'SUM4') AND ((size(dark_DN))[1] ne 256) THEN $
         dark_DN = 16 * REBIN(dark_DN, 256, 256)
      
      dark_message='Subtracted dark file = '+DarkFName
     
   endif else begin
      IF DebugFlag gt 0 THEN BEGIN
         CISSCAL_Log,'  Dark file '+DarkFName+' not found. Skipping dark subtraction...'
         IF IBatch ge 0 THEN CISSCAL_Log,'    for IBatch = '+strtrim(string(IBatch),2)
      ENDIF
      RETURN
   endelse
   
endif else begin 

; CISSCAL DARK/RBI MODEL:
;   - if removing hot pixels, determine appropriate hot pixel file
;   - construct dark file name from image parameters
;   - if dark file doesn't already exist, create new dark via interpolation
;     and save to appropriate subdirectory

   if camera eq 'ISSNA' then begin
      ESatPoint = 1.237e5     ; from values in params file
      cam = 'NAC'
      dparamfile='nac_dark_parameters.xdr'
   endif
        
   if camera eq 'ISSWA' then begin
      ESatPoint = 1.133e5     ; from values in params file
      cam = 'WAC'       
      dparamfile='wac_dark_parameters.xdr'
   endif

   ; determine appropriate hot pixel file:
   if dohot then begin

   ; First determine nearest hot pixel epoch from image date:
   ; extract day and year, estimate decimal year of image:

      ImgTime = self->GetLabel('IMAGE_TIME')
      ImgTimeY = STRMID(ImgTime,0,4)
      ImgTimeD = STRMID(ImgTime,5,3)
      ImgTimeYF = (ImgTimeY + (ImgTimeD / 365.25))[0]
      
      hotfilelist = file_search(CalibrationBaseDir + 'darkcurrent/' + cam + '_hotpix*')
   
      ypos = strpos(hotfilelist[0],'hotpix')
      YFs = strmid(hotfilelist,ypos+6,6)
       
      yearindex = (where(abs(YFs-ImgTimeYF) eq min(abs(YFs-ImgTimeYF))))[0]
   
      hotfile = hotfilelist[yearindex]
      subscript = YFs[yearindex]
   endif else begin
      hotfile = ''
      subscript = ''
   endelse

   ; Now construct dark file name...

   ; first get extra label info
   drf = self.Labels -> Get('DELAYED_READOUT_FLAG')
   if (drf EQ 'NO') then btsm = 0
   if (drf EQ 'YES') then btsm = 1
   
   telem_rate = self.Labels -> Get('INSTRUMENT_DATA_RATE')
   cdsr = 24                    ; assume as default
   
   if (telem_rate GE  60. AND telem_rate LE  61.) then cdsr = 8
   if (telem_rate GE 121. AND telem_rate LE 122.) then cdsr = 16
   if (telem_rate GE 182. AND telem_rate LE 183.) then cdsr = 24
   if (telem_rate GE 243. AND telem_rate LE 244.) then cdsr = 32
   if (telem_rate GE 304. AND telem_rate LE 305.) then cdsr = 40
   if (telem_rate GE 365. AND telem_rate LE 366.) then cdsr = 48
   
   ratio = 1.0
   if (comp NE 'NOTCOMP') then begin
      ratio = self.Labels -> Get('INST_CMPRS_RATIO')
      ratio = float(ratio)
      if ratio eq -1 then $
         ratio = self.Labels -> Get('COMPRESSION_RATIO')
   endif
   
   rate = self.Labels -> Get('INSTRUMENT_DATA_RATE')
   roindex = self.Labels -> Get('READOUT_CYCLE_INDEX')
   
   if ptr_valid(self.BinaryHdrP) then begin
      bh = *self.BinaryHdrP
      roo = bh[50]/32 MOD 2     ; Readout order is the 3rd bit of the 51st byte
   endif else begin
      roo = 0                   ; assume to avoid crash on old (pre-CISSCAL 3.7) calibrated images,
   endelse                      ; which lack a binary header
   
    ; look for file with correct camera parameters:
    dfname = darkfilename(sum, exp, conv, comp, $
                          btsm, cdsr, ratio, roindex, cam, roo, subscript, fsw)

    dfdir = CalibrationBaseDir + 'darkcurrent/darks' + subscript
    dfpath = dfdir + '/' + dfname

    if file_test(dfpath) then begin ; found file
       
       IF DebugFlag gt 0 THEN CISSCAL_Log,'  Reading dark file '+dfname+'...'

       DarkObj = OBJ_NEW('CassImg')
       DarkObj->ReadVic, dfpath, /Quiet, /NotCass
       dark_DN = DarkObj->Image() 
       dhist = DarkObj.Labels -> Get('PROCESSING_HISTORY_TEXT')

       if strmid(dhist,0,4) eq 'Dark' then begin ; use dark if file created by CISSCAL 3.7 or later
          havedark = 1
       endif else begin                          ; otherwise, create new dark and overwrite the old
          havedark = 0
          dmsg = '  Dark file is out of date'
       endelse
       
       OBJ_DESTROY, DarkObj     ; Finished with object: reclaim the space
       
    endif else begin
       havedark = 0
       dmsg = '  No dark file matching image parameters'
    endelse
    
    ; No dark file found; create new dark from model:

    if havedark eq 0 then begin

       IF DebugFlag gt 0 THEN BEGIN
          CISSCAL_Log, dmsg
          CISSCAL_Log,'    Creating new dark file '+dfname
          CISSCAL_Log,'    (This may take several minutes...)'
       ENDIF
                                ; create directory if necessary:
       
       if not file_test(dfdir,/directory) then begin
          dfdirsplit = strsplit(dfdir,' ',/extract)    ; this accounts for path names containing
          if n_elements(dfdirsplit) gt 1 then begin    ; blank spaces
             dfdirstr = dfdirsplit[0]
             for i = 1,n_elements(dfdirsplit)-1 do dfdirstr = dfdirstr + '\ ' + dfdirsplit[i]
          endif else begin
             dfdirstr = dfdirsplit
          endelse
          mkdirstring = 'mkdir ' + dfdirstr
          spawn,mkdirstring
       endif
 
       dark_e = makedarkarray(sum, exp, conv, comp, $
                              btsm, cdsr, ratio, roindex, cam, roo, dparamfile, hotfile, fsw)

       notzero = where(dark_e ne 0.0,nnz) ; this part probably not 
       if nnz ne 0 then begin             ; necessary once linetime fixed

           ; correct for gain:        
          IF camera EQ 'ISSNA' THEN BEGIN
             Gain2 = 30.27
             GainRatios = [0.135386, 0.309569, 1.0, 2.357285]
          ENDIF ELSE IF camera EQ 'ISSWA' THEN BEGIN
             Gain2 = 27.68
             GainRatios = [0.125446, 0.290637, 1.0, 2.360374]
          ENDIF 
            
          dark_DN = dark_e / (Gain2/GainRatios[GainState])
           
           ; check for both DN and full-well saturation:
          saturated = where(dark_DN ge DNSatPoint or dark_e ge ESatPoint,nsat)
          if nsat gt 0 then dark_DN[saturated] = DNSatPoint

          self->WriteVic,dfpath,dark=dark_DN
          
       endif else begin
          IF DebugFlag gt 0 THEN BEGIN
             CISSCAL_Log,'  Error in dark simulation; dark file not saved.'
             RETURN
          ENDIF
       endelse
       
    endif
    
    dark_message='Interpolation method'

endelse

; Add saturated dark pixels to saturated pixel array:
saturated = where(dark_DN ge DNSatPoint,nsat)
if nsat gt 0 then begin
   if not ptr_valid(self.SaturatedP) then self.SaturatedP = ptr_new(dark_DN ge DNSatPoint) else $
      *self.SaturatedP = *self.SaturatedP or (dark_DN ge DNSatPoint)
endif

*self.ImageP = *self.ImageP - dark_DN

;	Update calibration history in image label:
;		(added by Ben Knowles, 4/02)
;               (revamped for CISSCAL 3.7, 4/13)

junk=self.Labels->Set('DARK_CURRENT_CORRECTION_TYPE',dark_message,1,/new)
if dparamfile ne '' then $
   junk=self.Labels->Set('DARK_CURRENT_PARAM_FILE',dparamfile,1,/new)

If DebugFlag gt 0 THEN CISSCAL_Log,'  ',dark_message

  IF DebugFlag eq 2 THEN begin
      CISSCAL_Log, '  DN Extrema after dark subtraction', self->DNRange()
  ENDIF

END
