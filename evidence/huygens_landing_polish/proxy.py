"""A test server for one page: serves PAGE as / and /index.html, and passes every other GET through to UPSTREAM
(a running preview, read only). Nothing is written anywhere.
    python3 proxy.py PORT PAGE UPSTREAM [HOST]
"""
import http.client
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT, PAGE, UPSTREAM = int(sys.argv[1]), sys.argv[2], urllib.parse.urlsplit(sys.argv[3])
HOST = sys.argv[4] if len(sys.argv) > 4 else "127.0.0.1"
HOP = {"connection", "keep-alive", "transfer-encoding", "proxy-authenticate", "proxy-authorization", "te", "trailers", "upgrade"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _page(self, head):
        with open(PAGE, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _pass(self, method):
        path = urllib.parse.urlsplit(self.path).path
        if method in ("GET", "HEAD") and path in ("/", "/index.html"):
            return self._page(method == "HEAD")
        if method not in ("GET", "HEAD"):
            self.send_response(405); self.send_header("Content-Length", "0"); self.end_headers()
            return
        conn = http.client.HTTPConnection(UPSTREAM.hostname, UPSTREAM.port, timeout=120)
        try:
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP and k.lower() != "host"}
            conn.request(method, self.path, headers=headers)
            r = conn.getresponse()
            body = r.read()
            self.send_response(r.status)
            for k, v in r.getheaders():
                if k.lower() not in HOP and k.lower() != "content-length":
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if method != "HEAD":
                self.wfile.write(body)
        except Exception as e:  # the upstream went away: say so, keep serving
            try:
                self.send_response(502); self.send_header("Content-Length", "0"); self.end_headers()
            except Exception:
                pass
            sys.stderr.write(f"upstream {self.path}: {e}\n")
        finally:
            conn.close()

    def do_GET(self):
        self._pass("GET")

    def do_HEAD(self):
        self._pass("HEAD")

    def do_POST(self):
        self._pass("POST")


ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
