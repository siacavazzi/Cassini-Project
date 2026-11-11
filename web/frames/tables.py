#!/usr/bin/env python3
"""
The public site's per-frame JSON, written once per pass (prebuild.py's tables phase): what the frame server's table
routes answer (web/public/policy.json, store "table"), as files the publisher uploads and the Worker reads
(web/public/tables.schema.json, keys.json tables). Nothing here works anything out: each part is the answer of the
same obs_mosaic function the route calls, for a frame of the pass, serialized as the route serializes it.

Under <out> (prebuild's --tables-out, by default <cache>/public-tables):

  table/pass/<pass id>/info.json                 obs_mosaic.pass_info without n (the Worker adds the alias's n)
  table/pass/<pass id>/kind.json                 obs_mosaic.kind_of, the mosaic route's warm=1 answer
  table/pass/<pass id>/steady/c<C>k<K>.json      obs_mosaic.steady_table, every movie pass: c1k0, c1k1, and c0k0,
                                                 c0k1 where Auto center leaves the pass as it is
  table/pass/<pass id>/fade/l1_<W>x<H>.json      obs_mosaic.fade_table, every mosaic movie, at the W x H of its
                                                 rolling pictures at 1024 and 512 (as the page asks: the picture's size)
  table/pass/<pass id>/maps/<m>.json             obs_mosaic.tile_map, every layout a frame's map is kept under
  table/alias/<shard>.json                       every frame of the shard that is in a pass: {p, n, m}
  work/<pass id>.json                            the pass's alias entries and notes, until finish() writes the shards
  coverage.json                                  finish(): every pass asked for, the parts it has, what is missing

A table the server would answer {"working": true} is never written: a steady table whose chains are not made yet has
them made first by the repo's own makers (steady_chain, exposure_chain, as prebuild's chains phase makes them), then
is asked again; anything still not final is listed as missing in coverage.json.
"""
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obs_mosaic  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(os.path.dirname(HERE), "public", "tables.schema.json")
ROLLING_SIZES = (1024, 512)   # the rolling pictures' sizes the prebuild makes and the public site serves (fade W x H)


def pass_id(u):
    """The pass's id in table keys (tables.schema.json): its prebuild item name, name_id."""
    return name_id("_".join(map(str, u["key"])))


def name_id(name):
    """A prebuild pass item's name as a pass id: any character outside [A-Za-z0-9_.-] made '-'."""
    return re.sub(r"[^A-Za-z0-9_.-]", "-", name)


def shard_of(frame_id):
    """keys.json shard_rule: the camera letter and the first five digits of the clock."""
    return frame_id[0] + frame_id[1:6]


def dumps(obj):
    """As the server's send_json serializes an answer."""
    return json.dumps(obj).encode()


# ---------- the frames of a pass ----------

_by_obs = None


def _observation_frames():
    """(target, observation, camera) -> [(frame id, seconds since 1970)] over the index, in time order."""
    global _by_obs
    if _by_obs is None:
        idx, _ = obs_mosaic._row_of()
        out = {}
        for i, tgt, obs, ins, t in zip(idx["id"].tolist(), idx["TARGET_NAME"].tolist(), idx["OBSERVATION_ID"].tolist(),
                                       idx["INSTRUMENT_ID"].tolist(), idx["seconds_1970"].astype(float).tolist()):
            out.setdefault((tgt, obs, "N" if ins == "ISSNA" else "W"), []).append((i, t))
        _by_obs = out
    return _by_obs


def members(u):
    """[(frame id, n)] of every frame of the index obs_mosaic.unit_of puts in pass u (its frames, and the repeat
    exposures units leaves out of them), n being unit_of's index: what every per-frame route is asked with."""
    first, last = u["frames"][0][3], u["last"]
    out = []
    for fid, t in _observation_frames().get(tuple(u["key"][:3]), ()):
        if t < first - 1 or t > last + 1:
            continue
        found = obs_mosaic.unit_of(fid)
        if found and tuple(found[0]["key"]) == tuple(u["key"]):
            out.append((fid, found[1]))
    return out


# ---------- one pass ----------

def _steady(fid, u, cache, centre, colour, notes):
    """steady_table as the route answers it once the pass's chains are made: asked, and when the answer is not final
    (working, or its exposure chain not made yet) the chains made by the repo's makers and asked again."""
    got = obs_mosaic.steady_table(fid, cache, centre, colour)
    if got and (got.get("working") or (got.get("local") and got.get("exposure") is None)):
        p = obs_mosaic.plan(u, cache)
        obs_mosaic.steady_chain(u, cache, p)
        obs_mosaic.exposure_chain(u, cache, p, colour, centre, 0)
        notes.append(f"chains made for c{int(centre)}k{int(colour)}")
        got = obs_mosaic.steady_table(fid, cache, centre, colour)
    return got


def _picture_size(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        return im.size


def pass_tables(u, cache, movie=False, uncentred=False):
    """Every part of pass u: ({relative path: bytes}, {frame id: alias entry}, notes, missing). movie: a movie pass
    (steady tables); uncentred: Auto center leaves it as it is (also the center=0 steady tables)."""
    pid = pass_id(u)
    frames = members(u)
    parts, alias, notes, missing = {}, {}, [], []
    if not frames:
        return parts, alias, ["no frame of the index is in this pass"], ["info", "kind"]
    drawn = [(f, n) for f, n in frames if n >= 0]
    fid = (drawn or frames)[0][0]
    base = f"table/pass/{pid}/"

    info = obs_mosaic.pass_info(fid, cache)
    if info is None:
        missing.append("info")
    else:
        info.pop("n", None)
        parts[base + "info.json"] = info
    kind = obs_mosaic.kind_of(fid, cache)
    parts[base + "kind.json"] = kind

    if movie and drawn:
        combos = [(True, False), (True, True)] + ([(False, False), (False, True)] if uncentred else [])
        for centre, colour in combos:
            name = f"steady/c{int(centre)}k{int(colour)}"
            got = _steady(drawn[0][0], u, cache, centre, colour, notes)
            if not got or got.get("working") or (got.get("local") and got.get("exposure") is None):
                missing.append(name)
            else:
                parts[base + name + ".json"] = got

    if u.get("kind") == "mosaic_movie" and drawn:
        sizes = set()
        last = {}
        for f, n in drawn:
            last[n] = f
        for size in ROLLING_SIZES:
            for n in sorted(last):
                made = obs_mosaic.rolling_webp(last[n], size, cache, 1)
                if made and made[0] is not None:
                    sizes.add(_picture_size(made[0]))
                else:
                    missing.append(f"rolling {size} at {n}")
        for W, H in sorted(sizes):
            got = obs_mosaic.fade_table(drawn[0][0], cache, 1, min(W, 4096), min(H, 4096))
            name = f"fade/l1_{W}x{H}"
            if not got or got.get("working"):
                missing.append(name)
            else:
                parts[base + name + ".json"] = got
        if not sizes:
            missing.append("fade")

    layout_of = {}
    if u["mosaic"] and drawn:
        first = {}
        for f, n in drawn:
            first.setdefault(n, f)
        kept = os.path.join(obs_mosaic.folder(u, cache), obs_mosaic.MAPS_DIR)
        for n, f in sorted(first.items()):
            made = obs_mosaic.layout(u, n, cache)
            if not made:
                continue
            path = base + f"maps/{made[5]}.json"
            if path in parts:
                layout_of[n] = made[5]
                continue
            # the map tile_map keeps for this layout (its own file, read as tile_map reads it, without working the
            # layout out a second time), else tile_map's answer, which keeps it
            try:
                with open(os.path.join(kept, made[5] + ".json")) as fh:
                    mapped = json.load(fh)
            except (OSError, ValueError):
                mapped = obs_mosaic.tile_map(f, cache)
            if not mapped:
                continue
            layout_of[n] = made[5]
            parts[path] = mapped

    for f, n in frames:
        entry = {"p": pid, "n": n}
        if n in layout_of:
            entry["m"] = layout_of[n]
        alias[f] = entry
    return {k: dumps(v) for k, v in parts.items()}, alias, notes, missing


def write(out, rel, data):
    path = os.path.join(out, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = f"{path}.{os.getpid()}.part"
    with open(part, "wb") as fh:
        fh.write(data)
    os.replace(part, path)


def make_pass(u, cache, out, movie=False, uncentred=False, versions=None):
    """Writes pass u's parts under out and its alias entries and notes to work/<pass id>.json (finish() joins them
    into the shards). Found, not made, when its work file is there for the same versions. The pass's frames."""
    pid = pass_id(u)
    work = os.path.join(out, "work", pid + ".json")
    try:
        with open(work) as fh:
            kept = json.load(fh)
        if kept.get("versions") == versions and not kept.get("errors"):
            return len(kept.get("alias", {}))
    except (OSError, ValueError):
        pass
    t0 = time.monotonic()
    parts, alias, notes, missing = pass_tables(u, cache, movie, uncentred)
    errors = []
    for rel, data in parts.items():
        bad = validate_part(rel, json.loads(data))
        if bad:
            errors.append(f"{rel}: {bad}")
            continue
        write(out, rel, data)
    for f, entry in alias.items():
        bad = check(entry, _alias_entry())
        if bad:
            errors.append(f"alias {f}: {bad}")
    write(out, os.path.relpath(work, out), json.dumps({
        "pass": pid, "key": list(u["key"]), "kind": u.get("kind"), "versions": versions,
        "parts": sorted(os.path.relpath(r, f"table/pass/{pid}") for r in parts), "missing": missing, "notes": notes,
        "errors": errors, "seconds": round(time.monotonic() - t0, 2), "alias": alias}).encode())
    if errors:
        raise ValueError("; ".join(errors)[:300])
    return len(alias)


def finish(out, expected=None):
    """The alias shards (table/alias/<shard>.json) from every pass's work file, and coverage.json: every pass
    asked for (expected: pass ids; None, those with a work file), its parts, and any without its tables."""
    shards, passes = {}, {}
    folder = os.path.join(out, "work")
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else ():
        if not name.endswith(".json"):
            continue
        with open(os.path.join(folder, name)) as fh:
            w = json.load(fh)
        passes[w["pass"]] = w
        for f, entry in w["alias"].items():
            shards.setdefault(shard_of(f), {})[f] = entry
    for shard, frames in shards.items():
        doc = {"shard": shard, "frames": dict(sorted(frames.items()))}
        bad = validate_part("alias", doc)
        if bad:
            raise ValueError(f"alias shard {shard}: {bad}")
        write(out, f"table/alias/{shard}.json", dumps(doc))
    expected = sorted(expected if expected is not None else passes)
    without = [p for p in expected if p not in passes or not {"info.json", "kind.json"} <= set(passes[p]["parts"])]
    gaps = {p: passes[p]["missing"] for p in expected if p in passes and passes[p]["missing"]}
    report = {"passes": len(expected), "written": sum(p in passes for p in expected), "shards": len(shards),
              "frames": sum(len(v) for v in shards.values()), "without_tables": without, "missing_parts": gaps,
              "errors": {p: passes[p]["errors"] for p in expected if p in passes and passes[p]["errors"]},
              "parts": {k: sum(1 for p in expected if p in passes for r in passes[p]["parts"] if r.startswith(k))
                        for k in ("info", "kind", "steady", "fade", "maps")},
              "seconds": round(sum(passes[p]["seconds"] for p in expected if p in passes), 1)}
    write(out, "coverage.json", json.dumps(report, indent=1).encode())
    return report


# ---------- validation against tables.schema.json ----------

_schema = None


def schema():
    global _schema
    if _schema is None:
        with open(SCHEMA) as fh:
            _schema = json.load(fh)
    return _schema


def _alias_entry():
    return schema()["$defs"]["alias_shard"]["properties"]["frames"]["additionalProperties"]


def part_of(rel):
    """The $defs entry a written file validates against, from its path."""
    if rel == "alias" or rel.startswith("table/alias/"):
        return "alias_shard"
    name = rel.split("/")[3] if rel.startswith("table/pass/") else rel
    return {"info.json": "info", "kind.json": "kind", "steady": "steady", "fade": "fade", "maps": "maps"}[name]


def validate_part(rel, doc):
    """None when doc is valid for its part, else why not (jsonschema when installed, else check below)."""
    name = part_of(rel)
    try:
        import jsonschema
    except ImportError:
        return check(doc, schema()["$defs"][name])
    v = jsonschema.Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": schema()["$defs"]})
    errs = sorted(v.iter_errors(doc), key=str)
    return errs[0].message[:200] if errs else None


_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _is(doc, t):
    if t == "integer":
        return isinstance(doc, int) and not isinstance(doc, bool)
    if t == "number":
        return isinstance(doc, (int, float)) and not isinstance(doc, bool)
    return isinstance(doc, _TYPES[t])


def check(doc, s, at="$"):
    """The subset of JSON Schema tables.schema.json uses (type, enum, const, pattern, required, properties,
    additionalProperties, propertyNames, items, prefixItems, not/required, $ref), for machines without jsonschema:
    None when doc fits s, else the first reason it does not."""
    if "$ref" in s:
        return check(doc, schema()["$defs"][s["$ref"].split("/")[-1]], at)
    if "type" in s:
        types = s["type"] if isinstance(s["type"], list) else [s["type"]]
        if not any(_is(doc, t) for t in types):
            return f"{at}: not {s['type']}"
    if "enum" in s and doc not in s["enum"]:
        return f"{at}: not one of {s['enum']}"
    if "const" in s and doc != s["const"]:
        return f"{at}: not {s['const']}"
    if "pattern" in s and isinstance(doc, str) and not re.search(s["pattern"], doc):
        return f"{at}: {doc!r} does not match {s['pattern']}"
    if isinstance(doc, dict):
        for k in s.get("required", ()):
            if k not in doc:
                return f"{at}: {k} missing"
        if "not" in s and all(k in doc for k in s["not"].get("required", ())) and s["not"].get("required"):
            return f"{at}: has {s['not']['required']}"
        props = s.get("properties", {})
        for k, v in doc.items():
            if "propertyNames" in s:
                bad = check(k, s["propertyNames"], f"{at}.{k}")
                if bad:
                    return bad
            if k in props:
                bad = check(v, props[k], f"{at}.{k}")
            elif s.get("additionalProperties") is False:
                bad = f"{at}: {k} not allowed"
            elif isinstance(s.get("additionalProperties"), dict):
                bad = check(v, s["additionalProperties"], f"{at}.{k}")
            else:
                bad = None
            if bad:
                return bad
    if isinstance(doc, list):
        pre = s.get("prefixItems", [])
        for i, v in enumerate(doc):
            sub = pre[i] if i < len(pre) else s.get("items")
            if isinstance(sub, dict):
                bad = check(v, sub, f"{at}[{i}]")
                if bad:
                    return bad
    return None
