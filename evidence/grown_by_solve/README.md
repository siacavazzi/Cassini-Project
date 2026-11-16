# A filter's mosaic kept by its tiles' places (audit finding 18): evidence

Made 2026-11-16 on the M5 MacBook, full inputs. Every pass built by `prebuild.py <phase> --only <its frames>
--threads 1` in a process of its own (`build_each.sh`, `run_all.sh`) into an empty cache; pictures compared file by
file and, where they differ, pixel by pixel (`cmp_pixels.py`).

Four builds of two toss-up passes that play as movies (Enceladus 088EN SECLNX001, 22 frames; the ring pass 108RI
MNRNGSHAD005, 29 frames), and two of four mosaic passes:

| build | what it is |
|---|---|
| main | 1a35acb4: a toss-up's mosaic grown a frame at a time, each frame solved on the tiles so far |
| #503 | 721736e1's code: the toss-up solved on all its tiles first |
| main's order with this fix | this branch (main + the fix), no #503 |
| #503 with this fix | this branch and #503 merged |

## The finished view no longer depends on the order it was grown in

Enceladus 088EN's finished mosaic view has one name in all four builds (`CL1-CL222_ma7788fc0...`: the same solve):

| build | the picture (SHA-1) |
|---|---|
| main | b29aff0a08 (14 of 22 tiles where earlier partial solves put them, up to 5.1 px of the view off) |
| #503 | 6a165524c7 |
| main's order with this fix | **6a165524c7** |
| #503 with this fix | **6a165524c7** |

Grown a frame at a time under 22 different solves, the pass now ends in the very picture the solved-first build
draws. `before_after_enceladus_main_order.png`: main's build beside the same order with the fix, at 17, 19, 21 and 22
tiles (the pictures of the same name that differ: the six with more than `GROW_FROM` = 16 tiles, the ones grown).

The ring pass's finished view also changes in main's order (its tiles are drawn where its solve has them:
7771283ab6 to c8c93e8267), but keeps main's name and ring fits: which tiles the ring registration fits is the
order question #503 answers, not this one. With #503 its picture is the same with or without this fix (5727db1a1e).

## Nothing changes where the pass is solved before it is drawn

| compared | pictures of the same name | identical | filter mosaics under a new name |
|---|---|---|---|
| four mosaic passes (two mosaic movies, a WAC color mosaic, a ring mosaic), this fix against main (`pictures_mosaics-vs-main.md`) | 823 | **823** | 26 of 57 |
| the two toss-ups, #503 with this fix against #503 (`pictures_both-vs-503.md`) | 753 | **753** | 41 of 51 |

Every served picture (1,024 and 512 px, recovery maps, rolling pictures) and every tile is byte-identical; only the
kept filter mosaics of tiles a solve moved have another name. Work is the same too (instructions retired, billions):
the four mosaic passes 1,422 / 1,344 / 2,058 / 1,985 on main and 1,422 / 1,344 / 2,059 / 1,985 with the fix; the
toss-ups 1,960 and 2,195 on #503, 1,961 and 2,197 with the fix.

## What a pass grown under partial solves pays

In main's order (also a cold pass a server grows, or a stretch ending in the middle of a pass), a solve that moves
earlier tiles means the mosaic is grown again from its first 16 tiles instead of from the picture before:

| pass | pictures of the same name that change | work on main | main's order with the fix |
|---|---|---|---|
| Enceladus 088EN (22 tiles) | 6 of 22 | 2,173 billion | 2,432 (+12%) |
| 108RI ring pass (29 tiles) | 13 of 22 | 2,089 | 2,177 (+4%) |

(`pictures_g18-vs-main.md`.) The pre-build does not pay this once #503 is in: no pass is then drawn before it is solved.

## Not changed here

- Which pictures a server finds made (`tossup_check.py`: 8 of 22 and 10 of 29 in main's order, with or without this
  fix; 22 of 22 and 29 of 29 with #503): the names asked are #503's matter.
- `dim_under`'s kept measure of each tile against the picture before it (`under1-<filter>.json`) is still taken where
  the tile was at the time. On Enceladus 088EN it differs by up to 4% between the two orders and no tile crosses its
  line (the finished pictures above are identical), but a tile just at the line could.
- `seams()` keeps its answers by tile count too; it is not in use (`SHARED_SEAMS` is off).
- A mosaic movie's rolling picture does not use the solve.

## An existing cache

Kept filter mosaics of tiles a solve moved are not found under their old names, so whatever composes from them again
on an old cache (the full view of #482 for a pass not rebuilt, a server's first picture of a pass at another size)
composes those from the tiles once more. Served pictures keep their names. No version is bumped.

## Image benchmark

The 51-picture set (`web/frames/image_bench.py`): **PASS (nothing changed): 51 of 51 items identical** to main 1a35acb4 on this branch at 32a691c5 (`image_benchmark/report.md`, `summary.json`; run 2026-11-16). The set's mosaics are all solved before they are drawn, so nothing there moves; what this fix moves is shown by the builds above.
