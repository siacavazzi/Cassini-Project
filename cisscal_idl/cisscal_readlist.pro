pro cisscal_readlist, input_file, list, nfiles, noheader=noheader
  compile_opt strictarr

  @cisscal_common.pro	; include COMMON definitions

; Read text file containing single-column list (of input filenames,
; for example)
;
; Input parameter:
;    input_file = name of input text file containing filenames
; Output parameters:
;    list = list of filenames
;    nfiles = number of filenames read
;
; Input file format is ASCII text beginning with a descriptive header followed
; with the data values.  The line immediately preceding the data must be the
; text: "\begindata".  
;
; If no header, use /noheader keyword.

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

    list = ''
    nfiles = 0
    close, ilun
    free_lun, ilun
    return
  endif


  lbuf = ptr_new(strarr(1000))
  nfiles = 0

  while not eof(ilun) do begin
    readf,ilun,text
    (*lbuf)[nfiles] = text
    nfiles = nfiles + 1
  endwhile

  close, ilun
  free_lun, ilun

  list = (*lbuf)[0:nfiles-1]

  ptr_free, lbuf
end
