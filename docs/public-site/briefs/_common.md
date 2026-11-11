Every brief in this folder starts from the same ground:

- **Repo** `siacavazzi/Cassini-Project`. Branch `claude/public-<wp>` off `main` (off `claude/project-thread-daouww`,
  the WP0 branch, until WP0 merges; then merge main in). The PR targets `main`.
- **Read first** `docs/public-site/README.md` (what changed, decisions D1 to D9, rules, gates), the contracts in
  `web/public/` (`policy.json`, `keys.json`, `headers.json`, `tables.schema.json`, `manifest.schema.json`) and
  `docs/compute-on-viewer.md`.
- **Own only your files.** Anything else is a request to the lead thread; a contract change is its own small PR with
  `python web/public/keys.py --fixtures`, `python web/public/test_contracts.py` and `node web/public/test_keys.mjs`.
- **Output-neutral**: no change to a picture, a cache name or a version string, and no version string in new code.
- **Evidence** in the PR and under `/mnt/project-files/public-<wp>/`: before and after, posted to Sam as each piece exists.
- **Review** through the review thread; merge only on Sam's "merge".
