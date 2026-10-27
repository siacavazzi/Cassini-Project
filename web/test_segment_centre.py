"""prebuild's Auto center rule for a stretch made ahead (segment_items' centre, via centred): a pass the server
centres on its body or turns north up is made in that view, as the camera window asks for it; any other pass, or
one whose view fails, is made as it is; Auto center off makes every picture as it is. Run: python web/test_segment_centre.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import prebuild  # noqa: E402

views = {"body": {"centre": True}, "north": {"centre": False, "north": True}, "plain": {"centre": False, "why": "a ring movie"}}


def view(frame_id):
    if frame_id == "broken":
        raise ValueError("no geometry")
    return views[frame_id]


prebuild.obs_mosaic.centre_view = view
assert prebuild.centred("body") == views["body"]
assert prebuild.centred("north") == views["north"]          # north up is a view the server makes too
assert prebuild.centred("plain") is None
assert prebuild.centred("broken") is None
print("ok")
