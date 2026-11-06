cd /Volumes/SAM_IAC_PHOTO/cassini-work/pipeposter && source env.sh && export C CASSINI_SPICE_CACHE=/Volumes/LaCie/claude_scratch_spk/usgs_render_spice_cache CASSINI_KEEP_SPICE_CACHE=1
for pair in 129DI:N1649319522_1 158DI:N1702390881_1 214TE:N1807468103_1; do
  k=${pair%%:*}; f=${pair##*:}; mkdir -p /Volumes/SAM_IAC_PHOTO/cassini-work/pipeposter/full/$k
  t=$( { /usr/bin/time -p ls /Volumes/LaCie >/dev/null; } 2>&1 | awk '/real/{print $2}'); echo "$k lacie ls $t s"
  if [ "${t%.*}" -ge 10 ]; then echo "STOP lacie slow"; break; fi
  ~/agents/bin/job update pipeposter-full "rendering $k" 
  (nice -n 10 $PY -I tiles.py $f /Volumes/SAM_IAC_PHOTO/cassini-work/pipeposter/full/$k && nice -n 10 $PY -I mosaic_stage.py $f /Volumes/SAM_IAC_PHOTO/cassini-work/pipeposter/full/$k) > full/$k.log 2>&1; echo "$k exit $?"
done
echo QUEUEDONE
