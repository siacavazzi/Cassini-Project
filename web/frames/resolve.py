"""
The cache-only resolver (public site, WP1): which file in the picture cache answers a request, without making
anything. Written as a signature by WP0 (the contracts, web/public/), so the publisher (WP3) and the server's --public
mode can be built against it while WP1 fills it in.

The rule WP1 keeps: resolve() takes each route's decisions from the route's own code (frame_server.get() and the
makers' naming helpers it splits out of webp, color_webp, processed_webp, obs_mosaic.mosaic_webp, movie_webp,
rolling_webp and the table functions), so it can never name a different file than the maker writes. It never makes a
picture, never starts background work (warm_frame, tiles_ahead, warm_movie, rolling_ahead, _map_later) and never
waits for a slot.

  answer = resolve("/frames/color.webp", {"ids": ["N1,N2,N3"], "size": ["1024"], "center": ["1"]}, cache)
  answer.kind     "file": answer.path is the cached file the server would send, answer.headers its X-* headers
                  "negative": a deliberate negative answer (Auto center's 404 with X-Center): answer.status,
                  answer.headers and answer.body are what the server sends
                  "none": the cache has no answer (not made yet, or not a picture this route makes)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

KINDS = ("file", "negative", "none")


@dataclass(frozen=True)
class Answer:
    kind: str                                   # one of KINDS
    status: int = 200                           # the HTTP status the server sends (200 for a file)
    path: Optional[str] = None                  # kind "file": the cached file, absolute
    mime: Optional[str] = None                  # kind "file": image/webp, image/png or application/json
    headers: Dict[str, str] = field(default_factory=dict)   # X-Composite, X-Movie, X-Reel, X-Thumb, X-Center
    body: Optional[bytes] = None                # kind "negative": the body the server sends (JSON)

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"kind is one of {KINDS}")
        if self.kind == "file" and not self.path:
            raise ValueError("a file answer names its path")


NONE = Answer("none", 404)


def resolve(path: str, query: Dict[str, List[str]], cache: str) -> Answer:
    """The cache's answer to GET path?query (query as urllib.parse.parse_qs gives it, as the server reads it), using the
    route's own decisions, without making a picture or starting background work. WP1 fills this in."""
    raise NotImplementedError("resolve() is written by WP1 (docs/public-site/briefs/WP1.md)")
