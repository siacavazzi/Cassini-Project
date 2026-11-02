pro dark_ref, sum, exp, conv, comp, btsm, cdsr, ratio, roindex, cam, fsw, gainstate, hotname, out
@cisscal_common.pro
  DebugFlag = 0
  CalibrationBaseDir = getenv('REFDIR') + '/'
  hotfile = hotname eq '' ? '' : CalibrationBaseDir + 'darkcurrent/' + hotname
  dparamfile = strlowcase(cam) + '_dark_parameters.xdr'
  t0 = systime(1)
  dark_e = makedarkarray(sum, exp, conv, comp, btsm, cdsr, ratio, roindex, cam, 0, dparamfile, hotfile, fsw)
  if cam eq 'NAC' then begin
     Gain2 = 30.27 & GainRatios = [0.135386, 0.309569, 1.0, 2.357285] & ESat = 1.237e5
  endif else begin
     Gain2 = 27.68 & GainRatios = [0.125446, 0.290637, 1.0, 2.360374] & ESat = 1.133e5
  endelse
  dark_DN = dark_e / (Gain2/GainRatios[gainstate])
  s = where(dark_DN ge 4095.0 or dark_e ge ESat, n)
  if n gt 0 then dark_DN[s] = 4095.0
  openw, lun, out, /get_lun
  writeu, lun, float(dark_DN)
  free_lun, lun
  print, 'DONE', out, systime(1) - t0
end
