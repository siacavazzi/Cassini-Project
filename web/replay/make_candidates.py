#!/usr/bin/env python3
"""
Writes web/replay/candidates.csv: the moments other searches found that nobody has picked for the Moments list yet,
one row each, for the Moments window's "potential" entries (hidden until the viewer asks for them).

  python web/replay/make_candidates.py --movies movie_catalog.csv --transits transit-moments.csv \
      --finds catalogue.csv --shortlist shortlist.csv

  movies    the movie catalog (every sequence of 10+ time steps of one camera, view and target, and the sky stares):
            all of them
  transits  the SPICE scan of moon transits, mutual events and eclipses: the strong ones (score 12 or more, the
            scan's own cutoff) not already in moments.csv
  finds     the whole-mission geometry and coverage sweep: every candidate not already picked (shortlist, or its
            "already" column) and not on an observation moments.csv lists

Columns: type (movie, transit, find), start_utc, end_utc, body, cam (N, W or NW), frames, steps (time steps, movies),
color (yes/no), label, why, obs (observation ids), ref (the row in its source). build_data.py turns it into
data/candidates.json.
"""
import argparse, csv, datetime, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
COLS = ["type", "start_utc", "end_utc", "body", "cam", "frames", "steps", "color", "label", "why", "obs", "ref"]


def iso(t):
    """2012-127T19:58:06.091 (day of year) or 2012-05-06T19:58:06 -> 2012-05-06T19:58:06"""
    m = re.match(r"^(\d{4})-(\d{3})T(\d\d:\d\d:\d\d)", t)
    if m:
        d = datetime.date(int(m.group(1)), 1, 1) + datetime.timedelta(days=int(m.group(2)) - 1)
        return f"{d.isoformat()}T{m.group(3)}"
    return t[:19]


def title(name):
    return " ".join(w.capitalize() for w in name.replace("_", " ").split())


def movies(path):
    for r in csv.DictReader(open(path, newline="")):
        body = r["target"].upper()
        sky = r["target_class"].startswith("sky")
        label = (f"{title(body)} stare" if body != "SKY" else "Star field stare") if sky else f"{title(body)} movie"
        why = f"{r['judged_as'].capitalize()}, a picture every {r['cadence_s']} s" if r["cadence_s"] else r["judged_as"].capitalize()
        yield {"type": "movie", "start_utc": iso(r["start_utc"]), "end_utc": iso(r["end_utc"]), "body": body,
               "cam": r["camera"][0], "frames": r["frames"], "steps": r["time_steps"], "color": r["color"],
               "label": label, "why": why, "obs": r["observations"], "ref": r["sequence"]}


KIND = {"occultation/transit": "{a} passes {b}", "transit across disc": "{a} crosses {b}'s disk",
        "transit limb crossing": "{a} crosses {b}'s limb", "sets/rises behind limb": "{a} sets or rises behind {b}"}


def transits(path, listed):
    for r in csv.DictReader(open(path, newline="")):
        if r["added"] == "True" or float(r["score"]) < 12 or set(r["observations"].split()) & listed:
            continue
        a, _, b = r["pair"].partition("/")
        a, b = title(a), title(b)
        k = r["kind"]
        label = KIND.get(k, "{a} in {b}'s shadow" if k.startswith("eclipse") else "{a} and {b}: " + k).format(a=a, b=b)
        cam = "".join(c for c, n in (("N", r["nac"]), ("W", r["wac"])) if int(n or 0))
        yield {"type": "transit", "start_utc": iso(r["start_utc"]), "end_utc": iso(r["end_utc"]), "body": a.upper(),
               "cam": cam, "frames": r["frames"], "steps": "", "color": "", "label": label,
               "why": f"{k.capitalize()}, {r['detail']}", "obs": r["observations"], "ref": f"transit scan #{r['rank']}"}


def finds(path, shortlist, listed):
    picked = {r["catalogue_rank"] for r in csv.DictReader(open(shortlist, newline=""))} if shortlist else set()
    for r in csv.DictReader(open(path, newline="")):
        if r["rank"] in picked or r["already"].strip() or set(r["observations"].split()) & listed:
            continue
        kind = re.sub(r"\s*\(.*\)$", "", r["kind"]).strip()
        body = r["targets"].split()[0].upper() if r["targets"].strip() else "SATURN"
        cam = "".join(c for c, n in (("N", r["nac"]), ("W", r["wac"])) if int(n or 0))
        why = r["metric"] + (f" ({r['also'].replace(' | ', ', ').lower()})" if r["also"].strip() else "")
        yield {"type": "find", "start_utc": iso(r["start_utc"]), "end_utc": iso(r["end_utc"]), "body": body,
               "cam": cam, "frames": r["frames"], "steps": "", "color": "",
               "label": f"{title(body)}: {kind[0].lower() + kind[1:]}" if kind else title(body), "why": why,
               "obs": r["observations"], "ref": f"{r['family']} sweep #{r['rank']}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--movies", required=True)
    ap.add_argument("--transits", required=True)
    ap.add_argument("--finds", required=True)
    ap.add_argument("--shortlist")
    ap.add_argument("--moments", default=os.path.join(HERE, "moments.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "candidates.csv"))
    a = ap.parse_args()
    listed = {o for r in csv.DictReader(open(a.moments, newline="")) for o in r["obs"].split()}
    rows = [*movies(a.movies), *transits(a.transits, listed), *finds(a.finds, a.shortlist, listed)]
    rows.sort(key=lambda r: (r["start_utc"], r["type"], r["ref"]))
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, COLS, lineterminator="\n")
        w.writeheader(); w.writerows(rows)
    n = {t: sum(r["type"] == t for r in rows) for t in ("movie", "transit", "find")}
    print(f"{a.out}: {len(rows)} rows, " + ", ".join(f"{v} {k}s" for k, v in n.items()))


if __name__ == "__main__":
    main()
