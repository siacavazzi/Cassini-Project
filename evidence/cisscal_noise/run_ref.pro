pro dump, obj, name
  img = obj->Image()
  openw, lun, name, /get_lun
  writeu, lun, float(img)
  free_lun, lun
end

pro run_ref, imname, outbase, imagemean=imagemean
@cisscal_common.pro
  DebugFlag = 1
  CisscalVers = '4.1'
  CalibrationBaseDir = '/tmp/claude-0/ref/'
  IBatch = 1
  opts = cisscal_readoptfile('', /default)
  if keyword_set(imagemean) then begin
     (*opts.bias).biasstripmean = 1l
     (*(*opts.twohz).imagemean).onoff = 1l
  endif
  CalOptions = ptr_new(opts)
  obj = obj_new('CassImg')
  obj->ReadVic, imname
  obj->TwelveBit
  dump, obj, outbase + '_0lut.f32'
  obj->DeBias
  dump, obj, outbase + '_1bias.f32'
  obj->TwoHz
  dump, obj, outbase + '_2twohz.f32'
  print, 'LINEBREAK', obj->LineBreak()
  obj->BrightDark
  dump, obj, outbase + '_3pairs.f32'
  print, 'SIZE', size(obj->Image(), /dim)
end
