; Stand-in for IDL's library SAVGOL (missing from GDL 1.0.4): the least-squares smoothing
; coefficients (order 0) of a polynomial of the given degree over nleft..nright points.
function savgol, nleft, nright, order, degree
  n = nleft + nright + 1
  a = dblarr(degree + 1, n)
  for i = 0, n - 1 do for j = 0, degree do a[j, i] = double(i - nleft)^j
  ata = transpose(a) ## a
  m = invert(ata, /double) ## transpose(a)
  return, reform(m[*, order])
end
