pro cisscal_readspec, input_file, lamda, data, npts, noheader=noheader
  compile_opt strictarr

  @cisscal_common.pro	; include COMMON definitions

; Read table of spectral data.
; 
; Input parameter:
;    input_file = name of text file containing spectral data
; Output parameters:
;    lamda = array of ascending wavelengths (nm)
;    data = array of spectral data, where data[i] corresponds to wavelength
;           lamda[i].
;    npts = number of data samples
;
; Input file format is ASCII text beginning with a descriptive header followed
; with the data values.  The line immediately preceding the data must be the
; text: "\begindata".  Each line of data contains two floating point numbers:
;
;     Column 1 = wavelength (nm)
;     Column 2 = data value (e.g. radiance, optical transmission)
; 
; The input table may be either ascending or descending in wavelength.  If
; descending, the table is reversed to output an ascending table.

  openr, ilun, input_file, /get_lun

  text = ''

  if not keyword_set(noheader) then begin      
      while not eof(ilun) do begin
          readf, ilun, text
          if strpos(text, '\begindata') ge 0 then break
      endwhile
  endif

  if eof(ilun) then begin
    IF DebugFlag gt 0 THEN CISSCal_Log,'Error reading file ' + input_file

    lamda = [200.0, 201.0]
    data = [1.0, 1.0]
    npts = 2l
    close, ilun
    free_lun, ilun
    return
  endif

  lbuf = ptr_new(fltarr(20000))
  dbuf = ptr_new(fltarr(20000))
  npts = 0

  while not eof(ilun) do begin
    readf,ilun,x,y
    (*lbuf)[npts] = x
    (*dbuf)[npts] = y
    npts = npts + 1
  endwhile

  close, ilun
  free_lun, ilun

  *lbuf = (*lbuf)[0:npts-1]
  *dbuf = (*dbuf)[0:npts-1]

  if ((*lbuf)[0] gt (*lbuf)[npts-1]) then begin
    ; wavelength is in descending order, reverse to ascending order
    *lbuf = reverse(*lbuf)
    *dbuf = reverse(*dbuf)
  endif

  lamda = *lbuf
  data  = *dbuf

  ptr_free, lbuf
  ptr_free, dbuf
end

