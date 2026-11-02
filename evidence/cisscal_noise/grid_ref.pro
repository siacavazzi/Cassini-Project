pro grid_ref
  ; line breaks over a grid of readouts, and the hum filter on fixed signals at several breaks
  openw, lun, '/tmp/claude-0/ref/out/linebreak_grid.txt', /get_lun
  convs = ['12BIT','TABLE']
  comps = ['NOTCOMP','LOSSLESS','LOSSY']
  cdsrs = [8,16,24,32,40,48]
  fsws = [1.2, 1.3, 1.4]
  ratios = [1.5, 2.0, 3.3, 6.1]
  for ic=0,1 do for ip=0,2 do for ir=0,5 do for ifs=0,2 do for ia=0,3 do for ib=0,1 do for ix=0,3 do begin
     rdind = ix*4 + 1
     t = cisscal_linetime('FULL', 1.0, convs[ic], comps[ip], ib, cdsrs[ir], 0, ratio=ratios[ia], rdind=rdind, $
                          camera='ISSNA', roo=0, fsw=fsws[ifs], line_break=lb)
     printf, lun, convs[ic], ' ', comps[ip], ' ', cdsrs[ir], ' ', fsws[ifs], ' ', ratios[ia], ' ', ib, ' ', rdind, ' ', lb
  endfor
  free_lun, lun
  n = 1024
  x = findgen(n)
  sig = 2.0*sin(2*!pi*x/41.3) + 1.3*sin(2*!pi*x/37.1 + 0.4) + 0.002*x + 5.0*exp(-((x-300)/200.)^2) + 0.3*cos(x*1.7)
  openw, lun, '/tmp/claude-0/ref/out/filterhum.f32', /get_lun
  writeu, lun, float(sig)
  foreach lb, [1024, 300, 600, 975, 52] do begin
     writeu, lun, float(filterhum_verbatim(sig+0.0, 'ISSNA', lb, 1))
     writeu, lun, float(filterhum_verbatim(sig+0.0, 'ISSWA', lb, 0))
  endforeach
  free_lun, lun
end
