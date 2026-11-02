pro dump, obj, name
  img = obj->Image()
  openw, lun, name, /get_lun
  writeu, lun, float(img)
  free_lun, lun
end

pro run_im, imname, outbase
@cisscal_common.pro
  DebugFlag = 1
  CisscalVers = '4.1'
  CalibrationBaseDir = '/tmp/claude-0/ref/'
  IBatch = 1
  opts = cisscal_readoptfile('', /default)
  (*opts.bias).biasstripmean = 1l
  (*(*opts.twohz).imagemean).onoff = 1l
  CalOptions = ptr_new(opts)
  obj = obj_new('CassImg')
  obj->ReadVic, imname
  obj->TwelveBit
  obj->DeBias
  dump, obj, outbase + '_1bias.f32'
  m = obj->Missing()
  openw, lun, outbase + '_missing.u8', /get_lun & writeu, lun, byte(m) & free_lun, lun
  obj->TwoHz
  dump, obj, outbase + '_2twohz.f32'
  k = obj->Mask()
  openw, lun, outbase + '_mask.u8', /get_lun & writeu, lun, byte(k) & free_lun, lun
end
