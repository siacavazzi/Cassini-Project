# WP9 · Integration on the rehearsal slice, and WP10 · Full publish and the 1,000-user check

Read `_common.md` first. Not Wave 1: these start when WP1 to WP8 have merged.

**WP9.** Build the rehearsal slice on main plus Wave 1 (the sampler cache, or 2004-06-01 to 07-15 as the
logistics plan had it), run WP2's tables and fullview phases, publish to the mirror and to staging R2 once WP8 is live,
serve it through the Worker, and run every harness session. Fixes go as small PRs to the owning package. Done at gate G2.

**WP10.** Run the tables and fullview phases on the full cache, publish every year, run the harness on ten stretches
spread over the mission, measure requests and bytes per viewer-minute and turn them into cost at 1,000 viewers, then run
100 simulated viewers from a cloud runner (not the Mini's uplink) for latency and errors. Done at gate G3, then Sam's
word for G4.
