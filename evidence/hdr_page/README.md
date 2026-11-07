# HDR highlights in the camera windows (viewer side of #361)

Test server: this branch on 127.0.0.1:8930 with a copy of the #361 parity cache (`prebuild.py composites` and
`processed` for 80 frames, so it holds recovery maps), Chrome 157 headless. `run.py` opens 2006-09-15T09:23:10
(ISS_028RI_HIPHASE001_VIMS, Saturn backlit) three ways and lists the camera pictures asked for; `requests.json`.

- **HDR screen (matchMedia `(dynamic-range: high)` true), HDR highlights Auto:** composites and processed frames
  at 512 and 1024 are asked with `&hdr=1`. The ones with a map come back `image/avif` (`X-HDR: 1`), for example the
  backlit set W1537005244/261/278 at 1024 and 512. Pictures with no map yet, or asked while another AVIF was being
  made, come back as the usual WebP (`X-HDR: 0`), not kept by the browser. Strip pictures (256) never ask.
- **SDR screen:** 0 of 27 pictures asked with `hdr=1`. The addresses are the same as on main.
- **HDR screen, HDR highlights Off:** 0 of 27 asked with `hdr=1`.

Highlight glow (`glow.py`): 100% sets `dynamic-range-limit: no-limit` on the page's images, 40% sets
`dynamic-range-limit-mix(standard 60%, no-limit 40%)`, and 0% sets `standard`. Chrome applies all three.

Headless Chrome cannot show HDR in a screenshot. The pictures themselves are in `evidence/hdr_stills` (#361).
