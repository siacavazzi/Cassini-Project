"""Every movie pass on main (wt-sc5, 30d4960): which frames' own pictures never play in movie mode (color on),
by the server's rule (shown_of: plays_colour + set_of, else step_frame), all frames taken as fit and placed
(so a lower bound: unfit frames are held too). JSON lines, one per movie pass."""
import json, os, sys
sys.path.insert(0, os.path.expanduser("/Volumes/SAM_IAC_PHOTO/cassini-work/wt-colorhold/web/frames"))
import obs_mosaic as om, reel
idx, _ = reel.load_index()
out = open(sys.argv[1], "w")
for (target, ob, inst), rows in idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices.items():
    if not isinstance(ob, str):
        continue
    for u in om.units(target, ob, "N" if inst == "ISSNA" else "W"):
        fr = u["frames"]
        if not fr or not u.get("movie"):
            continue
        count, nms, aside, colour = om._filters(u)
        grey = max(count, key=count.get)
        filters = [f[2] for f in fr]
        t = [f[3] for f in fr]
        placed = lambda j: bool(fr[j][7])
        plays = bool(colour) and om.plays_colour(u, colour, grey)
        shown, setof = [], []
        for n in range(len(fr)):
            got, tint = om.set_shown(u, n, colour, lambda j: False, placed) if plays else (None, False)
            if got and not tint:
                shown.append(sorted(got.values())); setof.append(got)
            elif got and om.lum_of(fr, n, grey, placed, lambda j: True) is not None:
                shown.append([om.lum_of(fr, n, grey, placed, lambda j: True)]); setof.append(None)
            else:
                s = n
                if placed(n) and len(set(filters)) > 1:
                    s = om.step_frame(filters, n, grey, placed, lambda j: True, t)
                shown.append([s]); setof.append(None)
        seen = set(j for s in shown for j in s)
        hidden = [j for j in range(len(fr)) if j not in seen]
        # how far in time the picture shown is from the frame (its newest frame), and pictures from the future
        lag = [t[n] - t[max(s)] for n, s in enumerate(shown)]
        fut = sum(1 for x in lag if x < -1)
        # a hidden frame is a lost moment when the picture shown in its place was taken more than SET_GAP from it
        gap = om.sets_passes.SET_GAP
        lost = [j for j in hidden if abs(lag[j]) > gap]
        # runs of consecutive lost moments in time (the longest: how long the movie freezes)
        frz, best, a = [], 0, None
        for n in range(len(fr)):
            if n in set(lost):
                a = n if a is None else a
                best = max(best, t[n] - t[a])
            else:
                a = None
        rec = dict(target=target, obs=ob, cam=inst[-2], num=u["key"][3], n=len(fr), first=fr[0][1], colour=colour, grey=grey,
                   plays_colour=plays, sets=len(om._pass_sets(u)), distinct=len({tuple(s) for s in shown}),
                   hidden=len(hidden), hidden_grey=sum(1 for j in hidden if filters[j] == grey),
                   hidden_filters=sorted({filters[j] for j in hidden}), future=fut,
                   max_lag_s=round(max(abs(x) for x in lag)), span_s=round(t[-1] - t[0]),
                   hidden_ids=[fr[j][1] for j in hidden][:400], lost=len(lost), lost_grey=sum(1 for j in lost if filters[j]==grey), freeze_s=round(best), lost_ids=[fr[j][1] for j in lost][:400], first_t=t[0])
        out.write(json.dumps(rec) + "\n")
