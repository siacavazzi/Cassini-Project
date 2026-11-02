function cisscal_linetime, sum, exposure, conv, comp, btsm, cdsr, lline, $
              ratio=ratio, rdind=rdind, camera=camera, roo=roo, fsw=fsw, $
              line_break=line_break

;; Compute the time from light-flood erase to read out for a given image line.
;;
;; INPUTS:
;;	'sum' is the summation mode FULL, SUM2 or SUM4
;;	'exposure' is the exposure time in real seconds
;;	'conv' is conversion, 12BIT, TABLE, or 8LSB
;;	'comp' is NOTCOMP, LOSSLESS, LOSSY
;;	'btsm' is botsim (this is second image of botsim), 0 (no) or not 0 (yes)
;;	'cdsr' is the telemetry rate and is 8,16,24,32,40,or 48 packets per sec
;;	'lline' should range from 1 to 1024
;;
;;	'ratio' is compression ratio for current image
;;	'rdind' is readout index (needed for botsim wait)
;;	'camera'is NAC or WAC
;;      'roo'   is read out order (0=NAC first, 1=WAC first)
;;      'fsw'   is the version of flight software <1.4 or 1.4 and above
;;	if the last three are not given, assume camera is NAC and roo=0 and fsw=1.4
;;      (biu_swap will be wrong if camera=WAC and roo=0)
;;       
;;
;; OUTPUT: 'time' is the real seconds that 'lline' spends on the ccd

; This code originally derived from the Yagi/Girard 'linetime' subroutine which
; is from their 'PT' program

; Changes made were to include readout rate model from ITL and EGSE tests
; which include rates, BIU line break estimate and proper treatment of pads.
; BIU line break timing assumes shutter close at 0.461 into a second which
; occurs for images that start at the OFFSET_TIME given and are not delayed
; by previous images or by initial commands (e.g. commands before an OFFSET=0
; image.)  The BIU swap occurs during two rtis.  The readout rate into image
; buffer dependence vs. telemetry rate are accounted for by ratios to 48pps
; as determined by ITL test.  Readout rates and BIU line for LOSSLESS assumes
; constant compression ratio across image.  Thus if the top part of a frame
; has a much higher compression ratio than the frame average, the actual line
; when the BIU swap occurs will be later than this routine predicts.  A more
; accurate method would be to analyze the scene itself.  Flight software 1.4
; and above continues to read from the CCD during the BIU swap, 1.3 waits.
; It also fully uses the Image buffer, correcting a bug in flight software 1.3.
; - V. Haemmerle 11/9/2005
; Change fix() to long() to avoid negative line_breaks
; Change (r2 eq r1) to (r2 ge r1) to avoid negative line_breaks
; - V. Haemmerle 7/25/2006
; Modified to a function for incorporation into CISSCAL
; Added line_break return variable
; - B. Knowles 10/28/2013

; Readout rates
; r0 = rate when not creating science packets (e.g. second camera during 1st window)
; r1 = rate when creating science packets (normal readout rate)
; r2 = rate when limited to telemetry rate (slow down due to filled image buffer)
;
; Two improvements are possible to this model:
; a) Adjust the readout rates r0, r1 and r2 for LOSSLESS mode
;    to the scene compression ratio on a line pair basis
;    r0 and r1 depend on the current line being read out
;    r2 which applies to lines after the line break use 
;       the compression ratio at the start of the image
;       since those are the lines being packetized
;       i.e. readout at line x depends on ratio at line (x - line_break)
;    This would be helpful because the line break for 
;    FULL, 12BIT, LOSSLESS is very dependent on compression ratio
; b) For LOSSLESS mode, during the part of the image reading
;    out at rate r2 and with multiple lines per packet, the
;    general readout rate is r2 but when a packet is made and
;    room in the buffer is freed, the first line is read at the
;    expected r2 rate and the rest of the lines are readout at the
;    r1 rate until the buffer fills again, i.e. the readout plot is
;     a stairstep.
; 

  nlines = [1024,512,256]
  if (sum eq 'FULL') then sindex = 0 $
  else if (sum eq 'SUM2') then sindex = 1 $
  else if (sum eq 'SUM4') then sindex = 2

  tlm = cdsr/8
  t0 = exposure + .020  		;time from erase to first line
  t0 = t0 + 0.68*(nlines[sindex] - lline)/float(nlines[sindex])
  					;time due to 680ms erase
  line = lline-1 			;line is from 0 to 1023
  if line lt 0 then line = 0
  if line ge nlines[sindex] then line = nlines[sindex]-1

  ; Lossy mode streams CCD to Hardware compressor
  ; Flight software does not read CCD line-by-line.
  ; Rate does not depend on conversion mode (TABLE or 8LSB).
  ; Lossy streams even during BIU swap, so there is no BIU wait.
  ; Rates below were measured in EGSE and ITL tests, they did
  ; not depend on compression ratio or telemetry rate.
  if comp eq 'LOSSY' then begin
    r1 = [ 89.754, 110.131, 201.734 ]
    time = t0 + line/r1[sindex]
    line_break = 1024
    return,time
  endif

  if (not keyword_set(fsw)) then fsw = 1.4
  if (conv EQ '12BIT') then cindex = 0 $
  else cindex = 1
  if (not keyword_set(ratio)) then ratio = 2.
  if (comp eq 'NOTCOMP') then ratio = 1.
  correction = 1.
  data = [16.,8.]

  ; Telemetry rate factors (0,8,16,24,32,40,48 pps)
  ; The fastest science packet production rate is 48 packets per second.
  ; When the camera is creating less packets per second, it can have more
  ; time to service the CCD.  This can lead to a faster readout.  This
  ; effect is mostly seen in full or non compressed modes.

  telem_nc = [ [ 1.0161, 1.0128, 1.0095, 1.0082, 1.0031, 1.0033, 1.0 ], $ ;// full, not converted
               [ 1.0297, 1.0296, 1.0252, 1.0148, 1.0114, 1.0071, 1.0 ], $ ;// sum2, not converted
               [ 1.0356, 1.0320, 1.0260, 1.0201, 1.0128, 1.0057, 1.0 ], $ ;// sum4, not converted
               [ 1.0194, 1.0148, 1.0028, 1.0011, 1.0014, 1.0009, 1.0 ], $ ;// full, converted
               [ 1.0248, 1.0219, 1.0173, 1.0151, 1.0097, 1.0057, 1.0 ], $ ;// sum2, converted
               [ 1.0010, 1.0000, 0.9970, 0.9910, 0.9821, 0.9763, 1.0 ]  ] ;// sum4, converted

  telem_L   =[ [ 1.0276, 1.0284, 1.0182, 1.0122, 1.0048, 1.0016, 1.0 ], $ ;// full, not converted
               [ 1.0030, 0.9979, 0.9933, 0.9854, 0.9884, 1.0023, 1.0 ], $ ;// sum2, not converted
               [ 1.0011, 0.9976, 0.9894, 0.9864, 1.0000, 1.0000, 1.0 ], $ ;// sum4, not converted
               [ 1.0013, 1.0004, 0.9935, 0.9920, 1.0002, 0.9992, 1.0 ], $ ;// full, converted
               [ 1.0013, 0.9950, 1.0000, 1.0000, 1.0000, 1.0001, 1.0 ], $ ;// sum2, converted
               [ 0.9986, 0.9863, 1.0017, 1.0021, 1.0010, 1.0017, 1.0 ]  ] ;// sum4, converted


  case comp of
  'NOTCOMP': begin

  ;  Non-compressed modes
  ;  The following non-compressed rates were measured in ITL tests at 48
  ;  packets per second.  Rates are specified in lines per second.  The
  ;  values are for full, sum2 and sum4 modes.  Flight software timing
  ;  is accurate to 5ms, so rates are specified to 2 decimal places.

    rate_nc = [ [67.49, 85.11, 142.54 ], $  ; not converted
                [71.96, 88.99, 152.12 ]]    ; converted

  ;  Ratio of rate for FSW 1.4 vs 1.3 (EGSE tests at 48 and 24pps)
    correction_nc = [ [ 1.0027, 1.0073, 1.0087 ], $  ; not converted
                      [ 1.0016, 1.0042, 0.9946 ] ]   ; converted

    if (fsw GE 1.4) then correction = correction_nc[sindex,cindex]
    r1 = rate_nc[sindex,cindex] * telem_nc[tlm,sindex+3*cindex] * correction
    r0 = rate_nc[sindex,cindex] * telem_nc[0,sindex+3*cindex] * correction
  end


  'LOSSLESS': begin

  ; Lossless linear model
  ; The following are least square fits for Lossless modes at 48pps.  There is
  ; a fit for each summation mode and converted and not converted (12bit).

    rate0 = [ [ 67.673, 90.568, 150.593 ], $  ; not converted
              [ 74.862, 91.429, 152.350 ]]    ; converted
    slope = [ [ 1.6972, 0.3671, 0.4541 ], $   ; +/- 0.0102, 0.0255, 0.0450
              [ 0.4918, 0.4411, 0.5417 ]]     ; +/- 0.0069, 0.0182, 0.0697
  ;   RMS of fit  0.255   0.076   0.496    not converted
  ;   RMS of fit  0.172   0.162   0.429    converted

  ;  Ratio of rate for FSW 1.4 vs 1.3 (EGSE tests at 48 and 24pps)
   correction_L = [ [ 0.9999, 1.0034, 1.0073 ], $  ; not converted
                    [ 1.0019, 1.0050, 1.0080 ]]    ; converted

    if (fsw GE 1.4) then correction = correction_L[sindex,cindex]
    ro_ratefit = rate0[sindex,cindex] + slope[sindex,cindex]*ratio
    r1 = ro_ratefit * telem_L[tlm,sindex+3*cindex] * correction
    r0 = ro_ratefit * telem_L[0,sindex+3*cindex] * correction
  end

  else: return,-1
  endcase


  ; Calculation of BIU swap line which occurs upon completion of first packet
  ; If one or more complete lines can fit into the first packet of 440 words,
  ; they are moved from the Image Buffer allowing more to be read from the CCD
  ; before the BIU pause.
  ; Note: must also account for 4-word line header on each line
  tratio = ratio
  if (comp eq 'LOSSLESS' and tratio lt 2.) then tratio = 2.
  fpacket = 440/(4+long(nlines[sindex]*data[cindex]/16/tratio))
  biu_line = fpacket + 1

  ; if camera is opposite of read_out_order (second)
  ; Calculate number of lines read in early pad of 0.262 seconds
  ; BIU swap occurs after these number of lines or when
  ; first science packet is complete (at biu_line) which
  ; ever is greater
  second = 0
  if (n_elements(camera) ne 0 and n_elements(roo) ne 0) then begin
    if (camera eq 'NAC' and roo eq 1) then second = 1
    if (camera eq 'WAC' and roo eq 0) then second = 1
  endif
  ; First line after biu wait is at 0.289 seconds
  biutime = 0.289
  early_lines = 1
  if (second eq 1 and btsm eq 0) then begin
    early_lines = fix(0.262*r0) + 1
    if (early_lines GT biu_line) then biu_line = early_lines
    ; If there is 0.262 pad before readout window (i.e. second image)
    ; then biu swap occurs 2 rti later (0.25 sec)
    biutime = 0.539
  endif

  if sum ne 'FULL' then begin
    rate = r1
    if btsm ne 0 then rate = r0 ; No science packet rate
    if (btsm eq 0 and line ge biu_line and fsw LT 1.4) then $
       time = t0 + biutime + (line-biu_line)/rate $
    else time = t0 + line/rate
    line_break = 1024
    return,time
  endif

  ; Only FULL images can fill image buffer and cause r2 rate
  r2 = 3.5989*tlm ; ITL measured
  if (conv ne '12BIT') then r2 = 7.1989*tlm ; ITL measured
  ; For Lossless, r2 depends on compression ratio: but not faster than r1.
  if (comp eq 'LOSSLESS') then $
    ; r2 = cdsr * lines per packet
    ; lines per packet = data words per packet / data words per line
    ; data words per packet = (440 * 2% + 467 * 98%) - 4 (line header) = 462.46
    ; data words per line = 4 (line header) + (1024 or 512)/tratio
    r2 = cdsr*462.46/(4.+1024.*data[cindex]/16./tratio)
  r2 = min([r2,r1])

  ; Due to bug, FSW < 1.4 did not use 4K words of image buffer
  if (fsw lt 1.4) then buffer = 336 else buffer = 340
  if (conv ne '12BIT') then buffer = 2*buffer
  ; Stores 2 compressed lines into one 
  if (comp eq 'LOSSLESS') then buffer = 2*buffer
  ; Due to bug, FSW < 1.4 declared image buffer full with one free line
  if (fsw lt 1.4) then buffer = buffer - 1

  ; Now treat more complicated 1x1 case.
  if btsm eq 0 then begin

    if (fsw ge 1.4) then begin

      ; Calculate line break
      ; Transmit starts at biutime after readout starts
      ; after early_lines initially read before biutime
      ; buffer has buffer-inbuffer left to fill
      early_lines = fix(biutime*r0) + 1
      inbuffer = max([early_lines-fpacket,0])

      if (r2 ge r1) then line_break = 1024 $
      else line_break = early_lines + long(r1*(buffer-inbuffer)/(r1-r2)) + 1
      time = t0 + line/r1
      if (line gt line_break) then $
        time = t0 + line_break/r1 + (line-line_break)/r2

    endif else begin $

      ; Calculate line break
      ; Transmit starts and readout resumes at biutime
      ; after biu_lines initially read before biutime
      ; fpacket lines in 1st packet, max(early_lines-fpacket,0) in buffer
      inbuffer = max([early_lines-fpacket,0])

      if (r2 ge r1) then line_break = 1024 $
      else line_break = biu_line + long(r1*(buffer-inbuffer)/(r1-r2)) + 1
      time = t0 + line/r1
      if (line ge biu_line and line le line_break) then $
        time = t0 + biutime + (line-biu_line)/r1
      if (line gt line_break) then $
        time = t0 + biutime + (line_break-biu_line)/r1 + (line-line_break)/r2

    endelse

  endif else begin

    ; t1 is amount of time botsim image waits for first image readout window
    ; t1 only depends on readout index and telem rate:
    ; t1 is first camera readout window plus pad plus biu swap
    readout = [50,25,14,6]
    t1 = round(readout[rdind/4]*(6./float(tlm))) + 0.539
    time = t0 + line/r0
    line_break = buffer + fpacket + 1 ; Full buffer

    ; NOTCOMP 12BIT always stops and waits when buffer filled
    if (conv eq '12BIT' and comp eq 'NOTCOMP') then begin
      if (line ge line_break) then $
        time = t0 + t1 + (line-line_break)/r2
      return,time
    endif

    ; Line at which transmission starts
    ; Reading stops during BIU swap (0.25 sec) for FSW < 1.4
    if (fsw lt 1.4) then begin
      trans_line = long((t1-0.25)*r0) + 1
      biu_swap = 0.25
    endif else begin $
      trans_line = long(t1*r0) + 1
      biu_swap = 0.
    endelse

    ; NOTCOMP TABLE/8LSB may start reading out before buffer is filled
    ; LOSSLESS 12BIT may start reading out before buffer is filled
    ; If buffer is filled first, rest is read out at r2
    ; If t0+t1 occurs first then read continues at r1 until filled, then at r2
    if ((conv ne '12BIT' and comp eq 'NOTCOMP') OR (conv eq '12BIT' and comp eq 'LOSSLESS')) then begin
      if (trans_line ge line_break) then begin
        if (line ge line_break) then $
          time = t0 + t1 + (line-line_break)/r2 ; waits
      endif else begin
        if (r2 ge r1) then line_break = 1024 $
        else line_break = trans_line + long((line_break-trans_line)*r1/(r1-r2)) + 1

	if (line gt trans_line) then $
          time = t0 + trans_line/r0 + (line-trans_line)/r1 + biu_swap
	if (line gt line_break) then $
          time = t0 + trans_line/r0 + (line_break-trans_line)/r1 + $
                      (line-line_break)/r2 + biu_swap
      endelse
      return,time
    endif

    ; LOSSLESS with 8LSB or TABLE fits in image memory
    if (conv ne '12BIT' and comp eq 'LOSSLESS' and line gt trans_line) then begin
      time = t0 + trans_line/r0 + (line-trans_line)/r1 + biu_swap
    endif

  endelse

  return,time

end
