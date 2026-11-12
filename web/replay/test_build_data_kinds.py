"""build_data --groups stops when no pass has a kind (a build without CASSINI_GEOMETRY_CACHE), and goes on when some do.

    python web/replay/test_build_data_kinds.py

Offline: stands sets_passes in for one that answers fixed tables, so it needs no cache, kernels or geometry."""
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_data  # noqa: E402

FAILED = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        FAILED.append(what)


def run(passes):
    """load_groups() with a stand-in sets_passes whose groups() answers these passes; (SystemExit text or None, stdout)."""
    fake = types.ModuleType("sets_passes")
    fake.groups = lambda: ({}, {}, passes)
    real = sys.modules.get("sets_passes")
    sys.modules["sets_passes"] = fake
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            build_data.load_groups()
        return None, out.getvalue()
    except SystemExit as e:
        return str(e), out.getvalue()
    finally:
        if real is None:
            sys.modules.pop("sets_passes", None)
        else:
            sys.modules["sets_passes"] = real


def main():
    row = lambda kind: [kind, "ISS_006TI_EUVFUV001_UVIS", 0, "N1", 4, False]   # (kind first, as sets_passes writes it)
    stop, _ = run({"a": row(""), "b": row(""), "c": row("")})
    check(stop is not None and "none of the 3 passes has a kind" in stop and "CASSINI_GEOMETRY_CACHE" in stop,
          "no pass with a kind (no geometry cache) stops the build and names CASSINI_GEOMETRY_CACHE")
    stop, out = run({"a": row("mosaic"), "b": row(""), "c": row("movie")})
    check(stop is None and "groups: 2 of 3 passes with a kind" in out,
          "some passes with a kind: the build goes on and prints how many")
    stop, _ = run({})
    check(stop is None, "no passes at all (an empty year range) is not stopped")
    print(f"\n{len(FAILED)} failed" if FAILED else "\nall passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
