"""Movie candidates of the whole ISS index: one-view time series inside a pass, and series of passes of the same view
joined across observations. Input: passes2.jsonl (dump2.py, current main's obs_mosaic.units)."""
import json, os, re, sys, statistics as st, collections
sys.path.insert(0, os.path.expanduser("~/dev/wt-moviecat/web/frames"))
from obs_mosaic import RADIUS, SPECKS, IFOV

FLAG = re.compile(r"MOV|MV(?!E)")      # the observation's own name calls it a movie (MOVIE, MOV, MV: APPRMV, SPKMV)
STEP = 0.3        # frames: a same-filter step under this keeps the view (a pass the pipeline judges a mosaic or nothing)
DRIFT = 1.0       # frames: ... and the whole run stays within this of where it started
PLACE = 0.5       # frames: two pictures this close are one place (laps of a mosaic)
CREEP = 0.5       # a steady creep's steps stay within this share of their median step
LINK_GAP = 16 * 3600  # seconds: the most between two passes joined into one series
LOOKBACK = 3         # passes back a pass may match the view of
ZOOM = 1.4        # (obs_mosaic.ZOOM) the most the distance may change between two joined passes
BAND = (0.5, 2.0) # an interval within this of the median is on cadence
ON_CADENCE = 0.7  # share of intervals on cadence for a regular cadence
NONTARGETS = {"SKY", "UNK", "NONE", "DARKSKY", "STAR", "SUN", "CALIMG", "PLEIADES", "SPICA", "FOMALHAUT", "ARCTURUS", "VEGA",
              "ALDEBARAN", "ANTARES", "BETELGEUSE", "SIRIUS", "CANOPUS", "RIGEL", "ACHERNAR", "PROCYON", "CAPELLA", "POLARIS",
              "THETA_HYDRAE", "ALPHA_CENTAURI"}

def places(L):
    cent, cnt = [], []
    for t, x, y in L:
        if x is None: continue
        for j, c in enumerate(cent):
            if max(abs(x - c[0]), abs(y - c[1])) < PLACE:
                cnt[j] += 1; break
        else:
            cent.append((x, y)); cnt.append(1)
    return cent, cnt

def chain(L):
    """Longest run of one filter's pictures with every step under STEP and the run within DRIFT."""
    best, cur, ref, prev = [], [], None, None
    for t, x, y in L:
        if x is not None:
            if prev is not None and (max(abs(x - prev[0]), abs(y - prev[1])) >= STEP or max(abs(x - ref[0]), abs(y - ref[1])) > DRIFT):
                best = max(best, cur, key=len); cur = []; ref = None
            prev = (x, y); ref = ref or (x, y)
        cur.append(t)
    return max(best, cur, key=len)

def creep(L):
    """Longest run of one filter's placed pictures stepping on steadily: every step under STEP and within CREEP of the
    run's median step (a pan at an even pace, as a ring movie following the ring's own motion)."""
    pts = [(t, x, y) for t, x, y in L if x is not None]
    best, i = [], 0
    while i < len(pts) - 2:
        j = i + 1
        steps = []
        while j < len(pts):
            d = (pts[j][1] - pts[j - 1][1], pts[j][2] - pts[j - 1][2])
            if max(abs(d[0]), abs(d[1])) >= STEP: break
            if len(steps) >= 2:
                m = (st.median(a for a, _ in steps), st.median(b for _, b in steps))
                if max(abs(d[0] - m[0]), abs(d[1] - m[1])) > CREEP * max(abs(m[0]), abs(m[1]), 0.01): break
            steps.append(d); j += 1
        if j - i > len(best): best = [p[0] for p in pts[i:j]]
        i = j
    return best

def pass_view(p):
    """(epoch times of the pass's dominant filter, that filter, anchor (x, y) or None, how it was judged) or None
    when the pass is no one view taken again and again."""
    byf = collections.defaultdict(list)
    for fid, t, f, x, y in p["pics"]:
        byf[f].append((t, x, y))
    kind = p["kind"] or ""
    out = None
    for f, L in byf.items():
        xs = [x for _, x, _ in L if x is not None]; ys = [y for _, _, y in L if y is not None]
        anchor = (st.median(xs), st.median(ys)) if xs else None
        if kind == "movie":
            cand = ([t for t, _, _ in L], f, anchor, "movie")
        elif kind == "mosaic_movie":
            cent, cnt = places(L)
            if not cent: continue
            j = max(range(len(cnt)), key=lambda j: cnt[j])
            ts = [t for t, x, y in L if x is not None and max(abs(x - cent[j][0]), abs(y - cent[j][1])) < PLACE]
            cand = (ts, f, anchor, "laps")
        else:
            ts, how = chain(L), "stare"
            # a steady creep (the camera moving with a ring: an F ring movie), or a view taken again and again among
            # others (a spoke movie going back and forth between two patches of ring)
            c = creep(L)
            if len(c) > len(ts): ts, how = c, "creep"
            cent, cnt = places(L)
            if cent:
                j = max(range(len(cnt)), key=lambda j: cnt[j])
                lp = [t for t, x, y in L if x is not None and max(abs(x - cent[j][0]), abs(y - cent[j][1])) < PLACE]
                if len(lp) > len(ts) and len(cent) <= 4: ts, how = lp, "revisits"
            cand = (ts, f, anchor, how)
        if out is None or len(cand[0]) > len(out[0]):
            out = cand
    return out

def disk(S):
    """The target's diameter in full resolution pixels at the series' nearest (None: no size or distance known)."""
    r = RADIUS.get(S[0]["target"]) or SPECKS.get(S[0]["target"])
    zs = [p["z"] for p in S if p["z"]]
    if not r or not zs: return None
    return round(2 * r / (min(zs) * IFOV["N" if S[0]["cam"] == "ISSNA" else "W"]), 1)

def cadence(ts):
    d = [b - a for a, b in zip(ts, ts[1:]) if b > a]
    if not d: return None, 0.0
    m = st.median(d)
    return m, sum(BAND[0] * m <= x <= BAND[1] * m for x in d) / len(d)

def in_view(p, anchor):
    """The pass's target centre is in its frames (Auto center can hold a movie on it whatever the pointing)."""
    r = RADIUS.get(p["target"])
    if not r or not p["z"] or anchor is None:
        return False
    rf = r / (p["z"] * IFOV["N" if p["cam"] == "ISSNA" else "W"]) / 1024
    return max(abs(anchor[0]), abs(anchor[1])) < 0.5 + rf and rf >= 0.02

def linked(q, p):
    """Pass p takes the same view as pass q: one's dominant filter among the other's, near the same distance, and its pictures
    where q's were (within PLACE) or both on the target's disk (a body movie held by Auto center)."""
    v, vq = p["view"], q["view"]
    fq, fp = {x[2] for x in q["pics"]}, {x[2] for x in p["pics"]}
    if not (vq and (v[1] in fq or vq[1] in fp) and q["z"] and p["z"] and 1 / ZOOM < p["z"] / q["z"] < ZOOM and v[2] and vq[2]):
        return False
    a = (vq[2][0] * q["z"] / p["z"], vq[2][1] * q["z"] / p["z"])
    return max(abs(a[0] - v[2][0]), abs(a[1] - v[2][1])) < PLACE or in_view(q, vq[2]) and in_view(p, v[2])

def build(path, nmin):
    P = [json.loads(l) for l in open(path)]
    by = collections.defaultdict(list)
    for p in P:
        v = pass_view(p)
        p["view"] = v
        by[(p["target"], p["cam"])].append(p)
    seqs = []
    for (target, cam), L in by.items():
        # a pass joins the latest open series of the same view (other passes of the target may come between: a
        # satellite search between two approach movie frames); a series closes LINK_GAP after its last pass
        L.sort(key=lambda p: p["pics"][0][1])
        open_ = []
        for p in L:
            v = p["view"]
            if not v or not v[0]:
                continue
            t = p["pics"][0][1]
            for S in [S for S in open_ if t - S[-1]["pics"][-1][1] > LINK_GAP]:
                open_.remove(S); seqs.append(S)
            S = next((S for S in reversed(open_) if any(linked(q, p) for q in S[-LOOKBACK:])), None)
            if S is None:
                open_.append([p])
            else:
                S.append(p)
        seqs.extend(open_)
    out = []
    for S in seqs:
        ts = sorted(t for p in S for t in p["view"][0])
        if len(ts) < nmin: continue
        target, cam = S[0]["target"], S[0]["cam"]
        intra = [b - a for p in S for a, b in zip(p["view"][0], p["view"][0][1:]) if b > a]
        starts = [p["view"][0][0] for p in S]
        mi = st.median(intra) if intra else None
        ri = sum(BAND[0] * mi <= x <= BAND[1] * mi for x in intra) / len(intra) if intra else 1.0
        mo, ro = cadence(starts) if len(S) > 2 else (starts[1] - starts[0] if len(S) == 2 else None, 1.0)
        regular = ri >= ON_CADENCE and ro >= ON_CADENCE
        filters = collections.Counter(f for p in S for _, _, f, _, _ in p["pics"])
        obs = []
        for p in S:
            if p["obs"] not in obs: obs.append(p["obs"])
        kinds = [p["kind"] or "" for p in S]
        if len(S) == 1 and kinds[0] in ("movie", "mosaic_movie"):
            ours = "yes"
        elif any(k in ("movie", "mosaic_movie") for k in kinds):
            ours = "split"     # plays, but as several shorter movies
        else:
            ours = "no"
        pics = [q for p in S for q in p["pics"]]
        out.append(dict(
            seq=f"{target}/{obs[0]}/{cam}/{S[0]['num']}", passes=[p["pass_id"] for p in S], target=target,
            camera="NAC" if cam == "ISSNA" else "WAC", obs=obs, filters=[f for f, _ in filters.most_common()],
            colour=len([f for f in filters if f != "CL1/CL2"]) >= 2, frames=sum(p["taken"] for p in S), pictures=len(pics),
            steps=len(ts), dominant=S[0]["view"][1], how=sorted({p["view"][3] for p in S}),
            start=pics[0][1], end=pics[-1][1], first=pics[0][0], last=pics[-1][0],
            cadence=mi if mi is not None else mo, visit_period=mo if len(S) > 1 else None,
            on_cadence=round(min(ri, ro), 2), regular=regular, flagged=any(FLAG.search(o) for o in obs),
            ours=ours, kinds=sorted(set(kinds)), nontarget=target in NONTARGETS or target.endswith("SKY"),
            disk_px=disk(S),
            placed=round(sum(q[3] is not None for q in pics) / len(pics), 2)))
    return out

if __name__ == "__main__":
    nmin = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    out = build(sys.argv[1], nmin)
    json.dump(out, open(sys.argv[2], "w"))
    print(len(out))
