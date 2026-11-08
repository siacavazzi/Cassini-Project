"""pick.py OUT.json: the Jupiter set plus one centred color set per body spread over the mission, and one north pass."""
import sys, json, os
sys.path.insert(0, 'web/frames'); sys.path.insert(0, '.')
import frame_server as fs, reel, obs_mosaic as om
reel.load_index(); om._observations(); om._row_of()
picks = [{"ids": ["N1357349336_1", "N1357349290_1"], "body": "JUPITER", "why": "Sam's report"}]
picks[0]["view"] = om.centre_view("N1357349290_1")
north = None
for body in ["ENCELADUS", "TITAN", "DIONE", "RHEA", "SATURN", "MIMAS", "IAPETUS", "TETHYS"]:
    sh = [s for s in reel.shots(body) if s["kind"] == "true" and len(s["ids"]) >= 2]
    got = None
    n = len(sh)
    order = [int(n * f) for f in (0.5, 0.3, 0.7, 0.2, 0.8, 0.4, 0.6, 0.1, 0.9, 0.15, 0.85, 0.45, 0.55)]
    for k in order:
        s = sh[k]
        try:
            v = om.centre_view(s["ids"][-1])
        except Exception as e:
            print(body, k, "err", e); continue
        ang = reel.north_angles(s["ids"]).get(s["ids"][-1])
        print(body, k, s["ids"], v.get("centre"), v.get("north"), v.get("turn"), ang, flush=True)
        if v.get("north") and north is None:
            north = {"ids": s["ids"], "body": body, "view": v, "why": "close-up (north)"}
        if v.get("centre") and got is None and ang is not None and abs(((ang - v["turn"]) + 180) % 360 - 180) < 45:
            got = {"ids": s["ids"], "body": body, "view": v, "why": "centred"}
        if got and (north or body != "TITAN"):
            break
    if got: picks.append(got)
if north is None:
    for body in ["TITAN", "ENCELADUS", "SATURN", "DIONE", "RHEA"]:
        sh = [s for s in reel.shots(body) if s["kind"] == "true" and len(s["ids"]) >= 2]
        for s in sh[::max(1, len(sh)//60)]:
            v = om.centre_view(s["ids"][-1])
            if v.get("north"):
                north = {"ids": s["ids"], "body": body, "view": v, "why": "close-up (north)"}; break
        if north: break
if north: picks.append(north)
json.dump(picks, open(sys.argv[1], "w"), indent=1, default=str)
print(len(picks), "picks")
