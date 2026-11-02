pro lt_grid, out
  openw, lun, out, /get_lun
  sums = ['FULL','SUM2','SUM4'] & convs = ['12BIT','TABLE'] & comps = ['NOTCOMP','LOSSLESS','LOSSY']
  cdsrs = [8,16,24,32,40,48] & cams = ['NAC','WAC'] & fsws = [1.3, 1.4]
  nl = [1024,512,256]
  for a=0,2 do for b=0,1 do for c=0,2 do for d=0,5 do for e=0,1 do for f=0,1 do for g=0,1 do for h=0,1 do begin
    rd = (d*3 + c) mod 16
    ratio = 1.3 + 0.7*((a+d+e) mod 4)
    exps = [0.005, 1.2, 46.0, 320.0] & exp = exps[(b+c+d) mod 4]
    for l=1,nl[a],7 do begin
      t = cisscal_linetime(sums[a], exp, convs[b], comps[c], g, cdsrs[d], l, ratio=ratio, rdind=rd, camera=cams[e], roo=h, fsw=fsws[f])
      printf, lun, sums[a], exp, convs[b], comps[c], g, cdsrs[d], l, ratio, rd, cams[e], h, fsws[f], t, format='(A,1x,F0.4,1x,A,1x,A,1x,I0,1x,I0,1x,I0,1x,F0.2,1x,I0,1x,A,1x,I0,1x,F0.1,1x,E0.9)'
    endfor
  endfor
  free_lun, lun
end
