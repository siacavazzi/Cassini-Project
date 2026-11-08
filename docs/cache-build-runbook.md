# Cache build runbook: one build, several machines

How to build the whole picture cache with the Mac Mini and a second Mac (the M5 Pro MacBook Pro) at once, check it
and merge it into one cache. The tool is `web/frames/farm.py`; every picture is still made by `prebuild.py` (and so
by the frame server's own makers), one `--years` / `--from --until` slice at a time. Written for a Claude session on
each machine: nothing here needs a person at a keyboard, and nothing needs `sudo`.

## The shape of it

- **Hub**: the Mini. It holds the data drive (the Samsung T7, `/Volumes/SAM_IAC_PHOTO/cassini-work`), the shared
  farm folder (`cassini-work/farm`) and the final cache. It takes the whole-mission `frames` phase (archive reads,
  little CPU) and the lightest units.
- **Helper**: the laptop. It builds on its own internal disk from local copies of the inputs, takes the heaviest
  units, and ships each finished unit back to the hub over SSH, freeing its disk as it goes.
- **Units**: one per year; a year heavier than 6% of the mission is two halves (Jan-Jun, Jul-Dec). Each unit runs
  every phase in order: composites, processed, mosaics, movies, strips, chains (the r48 order).
- **Balancing**: both machines take from one list, the laptop from the heavy end, the Mini from the light end, so
  the build balances itself whatever the real speeds are. A claim is a `mkdir` in `farm/claims/`.

```
farm/farm.json         machines and settings (start from web/frames/farm.example.json)
farm/plan.json         units heaviest first, the commit and the Python packages' hash
farm/claims/<unit>/    taken; owner.json says by whom
farm/done/<unit>.json  finished: each phase's exit code and seconds
farm/logs/<machine>/phases.log
farm/stop-<machine>    touch it: that machine finishes its unit and stops
```

## Inputs each machine needs

| input | env var | size | hub (T7) | laptop (internal disk) |
|---|---|---|---|---|
| raw frames `cassini_lut8.zip` | `CASSINI_DATA` | 73 GB | `archives/` | local copy (random reads: never over the network) |
| zip index | `CASSINI_INDEX_CACHE` | small | `archives/zip_index` | copy the hub's folder (named by zip size + mtime, `cassini_lut8.zip-72996893446-1792490844`: copy the zip and the index with `rsync -a` so the mtime matches, or it re-indexes) |
| geometry `geometry-usgs.sqlite` (the USGS-refilled one main needs, never `geometry.sqlite`) | `CASSINI_GEOMETRY_CACHE` | 54 MB | `archives/` | local copy (written to: never share one file) |
| extracted SPICE cache (copy of `usgs_render_spice_cache`) | `CASSINI_SPICE_CACHE` | 16.4 GiB | `archives/spice_cache` | local copy |
| CISSCAL calibration | `CASSINI_CISSCAL` | 1.4 GiB | `archives/cisscal` | local copy |
| kernels `cassiniprojectJAN05.zip` | `CASSINI_KERNELS` | 131 GB | `archives/` | local copy, required: without it the laptop builds with only the kernels earlier renders unpacked (the 2017 test build's laptop months came out with other calibration numbers and failed movies). `run` refuses to start without it |
| repo at the plan's commit + `.venv` | | 0.8 GB | worktree | clone, `pip install` the hub's `pip freeze` |

`run` always sets `CASSINI_KEEP_SPICE_CACHE=1`.

T7 layout (all under `/Volumes/SAM_IAC_PHOTO/cassini-work/`): `archives/` (the inputs above, plus `cassiniprojectJAN05.zip` and the plain `geometry.sqlite`, which the farm doesn't use), `build-cache/` (the hub's cache, the frame server's `--cache`; `frames-q95` lands in it from the live prebuild), `build-cache-incoming-mbp/` (the laptop's shipped units, merged into `build-cache` by a move), `farm/` (the shared folder), `farm-mini/` (the Mini's status and logs).

`farm.py doctor --shared S --machine NAME` checks every input, the free space against `need_gb`, the commit and the
packages' hash against the plan, and (for the laptop) that SSH to the hub works.

## Free space

- **T7 (our part capped at ~1.2 TB; Sam's photos on the same volume are never touched)**: archives 204 GB + inputs
  ~17 GB + the cache 500-650 GB (the laptop's share arrives in `incoming-mbp/` and is *moved* into the cache, so it
  is never held twice) = ~720-870 GB.
- **Laptop**: inputs ~92 GB + about two units in flight (~60-70 GB each at most) + a 50 GB floor = **~300 GB free**
  with `"free": true`. Without freeing it needs ~550 GB (its whole share stays). Under 300 GB free: free space first,
  or run the Mini alone.

## Friday, step by step

1. **Freeze**: pick the commit. On the hub, make a clean worktree of it on the T7; `pip freeze` the venv into
   `farm/requirements-freeze.txt`.
2. **Hub inputs**: confirm the T7 copies of both zips and the geometry file are verified (size, member count, `cmp`
   of the ends). Copy `spice_cache` and `cisscal` into `archives/`. Build or copy the zip index for the T7 path.
   `frames-q95` didn't change (`FRAME_VERSION`): the lead copies the live prebuild's into `build-cache/frames-q95`,
   so the frames unit only fills gaps.
3. **SSH from the laptop to the hub**: on the laptop `ssh-keygen -t ed25519 -N '' -f ~/.ssh/cassini_farm`; on the
   Mini append the `.pub` line to `~/.ssh/authorized_keys`; on the laptop add a `Host mini` block (HostName
   192.168.68.54, User lazarus, IdentityFile ~/.ssh/cassini_farm). Remote Login is already on.
4. **Network**: measure it, both ways, before deciding how to preload:
   `time ssh mini 'head -c 4000000000 /Volumes/SAM_IAC_PHOTO/cassini-work/archives/cassini_lut8.zip' > /dev/null`
   and `time head -c 2000000000 /dev/zero | ssh mini 'cat > /dev/null'`. Faster than Wi-Fi when available: the Mini's
   Ethernet (1 GbE, ~110 MB/s) or a Thunderbolt cable between the two Macs (Thunderbolt Bridge, several hundred
   MB/s), each a cable plugged in, no setting changed.
5. **Laptop inputs**: `rsync -a --partial mini:/Volumes/SAM_IAC_PHOTO/cassini-work/archives/{cassini_lut8.zip,geometry-usgs.sqlite,cisscal,spice_cache,zip_index} ~/cassini-build/inputs/`
   (~91 GB: ~15-25 min at Wi-Fi's ~60-110 MB/s). Clone the repo at the commit; make the venv from the freeze.
6. **Config**: write `farm/farm.json` from `web/frames/farm.example.json` (`procs`: Mini 9, laptop
   16 to start). `farm.py plan --shared farm` writes plan.json and prints the estimate.
7. **Rehearsal (~1 h)**: both machines build the same short stretch, **from the years being built**, into scratch caches:
   `prebuild.py processed --from 2004-06-01 --until 2004-06-03 --cache <scratch> --procs N --balanced` and
   `movies` on the same stretch, then copy the laptop's scratch to the hub and `farm.py compare <mini scratch>
   <laptop scratch>`. Zero differences: go. Any: stop and report the files (the old plan found ≤0.0008 gray-level
   rounding between machines once; that is Sam's call). The same runs, timed, set `s_per_picture` and the laptop's
   `speed`; re-run `plan`.
8. **Go**: in a tmux session on each machine (laptop: also `caffeinate -dimsu`, on power, lid open or clamshell on
   power):
   `python web/frames/farm.py run --shared /Volumes/SAM_IAC_PHOTO/cassini-work/farm --machine mini`
   `python web/frames/farm.py run --shared ssh://mini/Volumes/SAM_IAC_PHOTO/cassini-work/farm --machine mbp`
   Each unit shows on the Mini dashboard (minidash :8787, Active jobs) as `farm-<machine>-<unit>`: `run` calls
   `~/agents/bin/job start/update/done/fail` itself (farm.json `"job"`), the laptop's units over SSH on the hub.
   The runs themselves are long jobs too: register each tmux session once,
   `~/agents/bin/job start farm-mini "cache build, Mini share" --tmux farm-mini --thread "<thread>" --eta +34h`
   (the laptop's: `ssh mini ~/agents/bin/job start farm-mbp "cache build, MacBook share" --thread "<thread>" --eta +34h`),
   and `job done` it when `run` ends.
9. **Watch**: `farm.py status --shared farm` (units done, building, waiting, each machine's last phase line). A
   failed phase is retried once; a unit still failing shows `FAILED <phase>` there and in `done/<unit>.json`: rerun
   it by deleting its `done/` file (keep the claim) and restarting that machine's `run`, which resumes its own claim
   first. To pause a machine: touch its `pause` file (prebuild waits); to stop it after the current unit: touch
   `farm/stop-<machine>`.
10. **Finish**: when `status` says all done and the laptop's last ship has ended:
    `farm.py merge --into build-cache --move build-cache-incoming-mbp` (moves files, keeps the hub's where both built one,
    e.g. a New Year pass, and lists any that differ), then `farm.py verify --cache build-cache --shared farm` (every
    unit, every phase recorded under this commit's versions, no errors). Then the pipeline's own completeness
    checks, before the cache is pointed at.

## Re-running later

A rebuild after a version bump is the same steps with a new commit and a fresh `build-cache/` (move the old one aside): a new
`farm/` folder (or empty `claims/`, `done/`, `logs/`), `plan`, rehearsal, `run`. Adding a machine is one more entry
in `machines` with its own `end`, `speed` and `ship_to`; the units and the claims don't change. A rebuild of a few
years only: `plan`, then delete from plan.json the units you don't want (or `verify --units`).

## Things that bit earlier builds

- The LaCie (exFAT spinner) serialises small-file I/O: one LaCie job at a time, and never a build cache on it.
- `prebuild.py --disk` runs `iostat` on the submitting thread and starves the pool: the farm always passes `--disk ''`.
- Run composites and processed as one-thread processes (`--procs`), `OPENBLAS_NUM_THREADS=1` (the farm sets it).
- macOS ships openrsync: `--remove-source-files` mis-handles folders, so the farm frees the laptop's disk itself,
  after a dry run shows every file is on the hub.
- Never `pkill` by a pattern that also matches the tmux wrapper; kill the Python child.
