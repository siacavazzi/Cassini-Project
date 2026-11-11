# Server refuses a site with no replay data

- `before_fresh_worktree.png`: regression-2017 (8c121d51) served from a fresh worktree on the Mini. The server starts,
  the page asks for `data/mission.json`, falls back to `data/bodies.json`, gets 404 for both and stops at
  "Could not load the trajectory files: data/bodies.json: 404" (what Sam hit on the 8955 and 8954 previews, 11-11).
- `after.txt`: the same fresh worktree on this branch. The server exits at once with the commands that make the data.
- `after_data_built_8955.png`: the 8955 preview (8c121d51) once `build_data.py --groups` + `build_coverage.py` output
  for that commit is in its worktree: the page loads.
