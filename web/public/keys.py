#!/usr/bin/env python3
"""
The public site's canonical keys (web/public/keys.json, policy.json): how a request to the frames host becomes the R2
object that answers it, or a refusal. The publisher (WP3) imports this module; the Worker (WP4) and the page's public
switch (WP5) use its line-for-line twin, keys.mjs. Both are tested against key_fixtures.json (test_keys.py,
test_keys.mjs), so they cannot drift.

  python web/public/keys.py '/frames/color.webp?ids=N1,N2,N3&size=1024&center=1'      prints the answer as JSON
  python web/public/keys.py --fixtures                                               writes key_fixtures.json's
                                                                                     answers from its cases

canonical(method, url, tags=None) -> dict:
  route     the policy route id, or None when no route fits
  store     r2, marker-capable r2, table, manifest, worker or refused (policy.json "stores")
  refused   None, or why the public site refuses it ("route: ..." or "param <name>: ...")
  key       r2: the object key, '{tag}' in place of the family's tag unless tags={family: tag} is given
  fallback  r2: keys to try, in order, when key is a miss (policy "fallback")
  params    the canonical parameters (only those that differ from the defaults, plus "keep" ones)
  download  True when download=1 asked for the picture as a named attachment
  table: frame, alias_key, part ('{m}' in a maps part is the alias entry's layout), answer (an answer that needs no
  object: a fade table asked at size 0, or a frame with no alias for mosaic_kind)
  manifest: field
"""
import hashlib
import json
import os
import re
import sys
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "keys.json")) as fh:
    KEYS = json.load(fh)
with open(os.path.join(HERE, "policy.json")) as fh:
    POLICY = json.load(fh)

FRAME_ID = re.compile(r"^[NW]\d{10}_\d+$")
CHARSET = re.compile(KEYS["value_charset"])
WHOLE = re.compile(r"^-?\d+$")
ALL_SIZES = KEYS["sizes"]["all_sizes"]
ROUTES = [dict(r, _re=re.compile(r["pattern"])) for r in POLICY["routes"]]


class Refused(Exception):
    pass


def parse_query(query):
    """name -> first value, as the server's parse_qs reads a query: blank values are as if missing, the first of a
    repeated name wins. Values are percent-decoded and '+' is a space."""
    from urllib.parse import unquote_plus
    out = {}
    for part in query.split("&") if query else []:
        name, eq, value = part.partition("=")
        name, value = unquote_plus(name), unquote_plus(value)
        if not eq or value == "" or name in out:
            continue
        out[name] = value
    return out


def family_tag(family, versions):
    """The family's tag for these picture-maker versions (keys.json families tag_rule)."""
    deps = [re.compile(d) for d in KEYS["families"]["list"][family]["depends"]]
    chosen = {k: v for k, v in versions.items() if any(d.search(k) for d in deps)}
    blob = json.dumps(chosen, sort_keys=True, separators=(",", ":")).encode()
    return "t" + hashlib.sha256(blob).hexdigest()[:12]


def family_tags(versions):
    """{family: tag} for every family, from frame_server.picture_versions()."""
    return {f: family_tag(f, versions) for f in KEYS["families"]["list"]}


def _size(v, spec):
    built = spec["built"]
    if v == "full":
        full = spec.get("full")
        if full is None:
            raise Refused("size full is not built for this route")
        if full == "full":
            return "full"
        v = str(full)
    if v is None or not WHOLE.match(v):
        n = spec["default"]
    else:
        asked = int(v)
        n = min(ALL_SIZES, key=lambda s: abs(s - asked))   # frame_server.size_of: the first of a tie wins
    if n not in built:
        above = [b for b in built if b >= n]
        n = min(above) if above else max(built)
    return str(n)


def _flag(v, spec):
    if v is None:
        n = spec["default"]
    elif spec["read"] == "not0":
        n = 0 if v == "0" else 1
    elif spec["read"] == "eq1":
        n = 1 if v == "1" else 0
    else:   # nonempty
        n = 1
    if "allowed" in spec and n not in spec["allowed"]:
        raise Refused(f"{n} is not offered on the public site")
    return str(n)


def _int(v, spec):
    if v is None:
        n = spec["default"]
    else:
        if not WHOLE.match(v):
            raise Refused("not a whole number")
        n = max(spec["min"], min(spec["max"], int(v)))
    if "allowed" in spec and n not in spec["allowed"]:
        raise Refused(f"{n} is not offered on the public site")
    return str(n)


def _enum(v, spec):
    v = spec["default"] if v is None else v
    if v not in spec["allowed"]:
        raise Refused(f"{v!r} is not offered on the public site")
    return v


def _id(v, spec):
    if v is None:
        return None
    if not FRAME_ID.match(v):
        raise Refused("not a frame id")
    return v


def _ids(v, spec):
    if v is None:
        return None
    ids = [i for i in v.split(",") if i]
    if not spec["min"] <= len(ids) <= spec["max"] or not all(FRAME_ID.match(i) for i in ids):
        raise Refused(f"takes {spec['min']} to {spec['max']} frame ids")
    if spec.get("same_camera") and len({i[0] for i in ids}) > 1:
        raise Refused("frame ids from one camera")
    return ",".join(ids)


READ = {"size": _size, "flag": _flag, "int": _int, "enum": _enum, "id": _id, "ids": _ids}


def _default(spec):
    if spec["type"] in ("id", "ids"):
        return None
    return str(spec["default"]) if spec.get("default") is not None else None


def route_of(method, path, q):
    for r in ROUTES:
        if r["method"] != method or not r["_re"].match(path):
            continue
        mq = r.get("match_query") or {}
        if all((name in q) if want == "*" else (q.get(name) == want) for name, want in mq.items()):
            return r
    return None


def _key(r, path, params, tags):
    tag = (tags or {}).get(r["family"], "{tag}")
    query = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return f"{r['family']}/{tag}/{path[1:]}" + (f"~{query}" if query else "")


def canonical(method, url, tags=None):
    """The public answer for method url (a path with its query, or a whole URL): see the module's docstring."""
    u = urlsplit(url)
    path, q = u.path, parse_query(u.query)
    out = {"route": None, "store": "refused", "refused": None, "key": None, "fallback": [], "params": {},
           "download": q.get("download") == "1"}
    r = route_of(method, path, q)
    if r is None:
        out["refused"] = "route: not a route of the frame server"
        return out
    out["route"], out["store"] = r["id"], r["store"]
    if r["store"] == "refused":
        out["refused"] = "route: " + r.get("why", "not on the public site")
        return out
    if r["store"] == "manifest":
        out["field"] = r["field"]
    if r["store"] in ("manifest", "worker"):
        return out
    g = KEYS["global"]
    specs = r.get("params", {})
    params = {}
    try:
        for name, v in q.items():
            if name in g["drop"] and name not in specs:
                continue
            if name in g["default_only"] and name not in specs:
                if v != g["default_only"][name]:
                    raise Refused(f"param {name}: only {g['default_only'][name]!r} is offered on the public site")
                continue
            if name not in specs:
                raise Refused(f"param {name}: not a parameter of this route")
        for name, spec in specs.items():
            if spec["type"] == "drop":
                continue
            try:
                v = READ[spec["type"]](q.get(name), spec)
            except Refused as e:
                raise Refused(f"param {name}: {e}")
            if v is None:
                if spec.get("required"):
                    raise Refused(f"param {name}: required")
                continue
            if v == _default(spec) and not spec.get("keep"):
                continue
            if not CHARSET.match(v):
                raise Refused(f"param {name}: characters the public site does not use")
            params[name] = v
        if r.get("require_one_of") and not any(n in params for n in r["require_one_of"]):
            raise Refused("param " + "|".join(r["require_one_of"]) + ": one of them is needed")
    except Refused as e:
        out["store"], out["refused"] = "refused", str(e)
        return out
    out["params"] = params
    groups = dict(zip(r.get("groups", []), r["_re"].match(path).groups()))
    if r["store"] == "table":
        frame = groups["id"]
        t = KEYS["tables"]
        tag = (tags or {}).get("table", "{tag}")
        part = t["parts"][r["part"]].format(center=params.get("center", "1"), color=params.get("color", "0"),
                                            laps=params.get("laps", "1"), w=params.get("w", "0"), h=params.get("h", "0"),
                                            m="{m}")
        out.update(frame=frame, part=part, alias_key=t["alias_key"].format(tag=tag, shard=frame[0] + frame[1:6]),
                   part_key=t["part_key"].replace("{tag}", tag).replace("{part}", part))
        if r.get("zero_size_answer") is not None and (params.get("w", "0") == "0" or params.get("h", "0") == "0"):
            out["answer"] = r["zero_size_answer"]
        if r.get("no_alias_answer") is not None:
            out["no_alias_answer"] = r["no_alias_answer"]
        return out
    out["family"] = r["family"]
    out["key"] = _key(r, path, params, tags)
    for fb in r.get("fallback", []):
        if all(params.get(k) == v for k, v in fb["when"].items()):
            p = dict(params)
            p.update(fb.get("set", {}))
            for k in fb.get("unset", []):
                p.pop(k, None)
            out["fallback"].append(_key(r, path, p, tags))
    if len(out["key"].encode()) > KEYS["max_key_bytes"]:
        out.update(store="refused", refused="key: longer than R2 allows", key=None, fallback=[])
    return out


def _main(argv):
    if argv and argv[0] == "--fixtures":
        path = os.path.join(HERE, "key_fixtures.json")
        with open(path) as fh:
            fx = json.load(fh)
        for case in fx["cases"]:
            case["expect"] = canonical(case.get("method", "GET"), case["url"])
        with open(path, "w") as fh:
            json.dump(fx, fh, indent=1)
            fh.write("\n")
        print(f"{len(fx['cases'])} cases written to {path}")
        return 0
    for url in argv:
        method, _, rest = url.partition(" ") if url.split(" ")[0] in ("GET", "POST", "PUT") else ("GET", "", url)
        print(json.dumps(canonical(method, rest), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
