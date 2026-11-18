# local page + _dn files; anything else (static data) fetched from Mini 8943; never /frames
import http.server, os, urllib.request, sys
ROOT = os.path.expanduser("~/cassini-build/denoise/wt/web/cassini-os")
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=ROOT, **k)
    def log_message(s, *a): pass
    def do_GET(s):
        p = s.path.split("?")[0]
        if p.startswith("/frames"): s.send_error(404); return
        if os.path.isfile(os.path.join(ROOT, p.lstrip("/"))) or p == "/": return super().do_GET()
        try:
            r = urllib.request.urlopen("http://192.168.68.59:8943" + s.path, timeout=60); b = r.read()
            s.send_response(200); s.send_header("Content-Type", r.headers.get("Content-Type", "application/octet-stream")); s.send_header("Content-Length", str(len(b))); s.end_headers(); s.wfile.write(b)
        except Exception: s.send_error(404)
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
