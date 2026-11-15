#!/usr/bin/env python3
"""
How fast publish.py uploads to R2, before and after a change, against a local stand-in for R2's S3 API over real TLS
with a network's delays added (no Cloudflare call, no credentials): each new connection waits --handshake round trips
(TCP and TLS), each request one round trip, each PUT --put seconds more (R2 writing the object). It times one process
storing --objects objects of --size bytes the way the publisher of each version does (the old: a HEAD and a PUT per
object, a new connection each; the new: kept-alive connections, --fresh, --uploads threads), then projects the whole
upload from those rates with the publish's CPU (--resolve-ms a URL per process), the --jobs processes and the uplink.

  python web/frames/bench_publish_upload.py [--before REF] [--objects 400] [--size 24000] [--rtt 0.03] [--put 0.08]
         [--jobs 18] [--uploads 16] [--total 9.6e6] [--gb 221.5] [--uplink-mbps 350] [--resolve-ms 6] [--json OUT]

--before REF   the git revision whose publish.py is "before" (default origin/public-release); the working tree's is "after"
The defaults: 24 KB is the measured cache's mean served file (221.5 GB / 9.34 M files); 30 ms a round trip and 80 ms
for R2 to write are assumptions (not measured from the house); 6 ms a URL is WP3's measured resolve-and-write time;
350 Mbps is about 70% of the Mini's measured 505 Mbps upload.
"""
import argparse
import hashlib
import http.server
import importlib
import json
import os
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)


class S3(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    rtt, put_s, handshake = 0.03, 0.08, 2
    objects, lock, counts = {}, threading.Lock(), {"connections": 0, "HEAD": 0, "PUT": 0}

    def setup(self):
        with S3.lock:
            S3.counts["connections"] += 1
        time.sleep(S3.handshake * S3.rtt)   # TCP + TLS before the first request
        super().setup()

    def log_message(self, *a):
        pass

    def _answer(self, status, headers=()):
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        with S3.lock:
            S3.counts["HEAD"] += 1
        time.sleep(S3.rtt)
        got = S3.objects.get(self.path)
        if got is None:
            return self._answer(404)
        self._answer(200, [("ETag", f'"{got[0]}"'), ("Content-Type", got[1])])

    def do_PUT(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with S3.lock:
            S3.counts["PUT"] += 1
        time.sleep(S3.rtt + S3.put_s)
        md5 = hashlib.md5(body).hexdigest()
        S3.objects[self.path] = (md5, self.headers.get("Content-Type"))
        self._answer(200, [("ETag", f'"{md5}"')])


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    request_queue_size = 512


def tls_server(tmp):
    cert, key = os.path.join(tmp, "cert.pem"), os.path.join(tmp, "key.pem")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", cert, "-days", "1",
                    "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"], check=True, capture_output=True)
    srv = Server(("127.0.0.1", 0), S3)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["SSL_CERT_FILE"] = cert   # the clients (urllib and http.client) trust the stand-in's certificate
    return srv


def load_before(ref):
    src = subprocess.run(["git", "-C", REPO, "show", f"{ref}:web/frames/publish.py"], check=True, capture_output=True,
                         text=True).stdout
    path = os.path.join(HERE, "_publish_before_bench.py")   # beside publish.py, so its own imports resolve as they did
    with open(path, "w") as fh:
        fh.write(src)
    try:
        return importlib.import_module("_publish_before_bench")
    finally:
        os.remove(path)


def rate(mod, env, n, size, tmp, name, **store_kw):
    """Objects a second one process stores (the old way or the new), from an empty ledger and bucket."""
    S3.objects.clear()
    for k in S3.counts:
        S3.counts[k] = 0
    r2 = mod.R2(env=env)
    led = mod.Ledger(os.path.join(tmp, name, "ledger.sqlite"))
    objs = [(f"bench/{name}/frames/N{1500000000 + i}_1.webp~size=512", os.urandom(size), "image/webp", {}, "whole")
            for i in range(n)]
    up = store_kw.pop("uploads", 0)
    uploader = mod.Uploader(up) if up else None
    t0 = time.monotonic()
    for o in objs:
        if uploader is not None:
            mod.store(r2, led, [o], uploader=uploader, **store_kw)
        else:
            mod.store(r2, led, [o], **store_kw)
    if uploader is not None:
        uploader.drain()
    took = time.monotonic() - t0
    return {"objects": n, "seconds": round(took, 2), "per_second": round(n / took, 1), **dict(S3.counts)}


def project(per_proc, a, overlap):
    """Hours for the whole upload: --jobs processes each resolving (CPU) and uploading; overlap: the uploads run beside
    the resolving (the new publisher's threads) instead of after it, one object at a time (the old)."""
    net_s = a.total / (per_proc * a.jobs)
    cpu_s = a.total * a.resolve_ms / 1000 / a.jobs
    wire_s = a.gb * 8e9 / (a.uplink_mbps * 1e6)
    proc_s = max(net_s, cpu_s) if overlap else net_s + cpu_s
    return {"network_h": round(net_s / 3600, 2), "cpu_h": round(cpu_s / 3600, 2), "uplink_h": round(wire_s / 3600, 2),
            "total_h": round(max(proc_s, wire_s) / 3600, 2)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--before", default="origin/public-release")
    ap.add_argument("--objects", type=int, default=400)
    ap.add_argument("--size", type=int, default=24000)
    ap.add_argument("--rtt", type=float, default=0.03)
    ap.add_argument("--put", type=float, default=0.08)
    ap.add_argument("--handshake", type=float, default=2)
    ap.add_argument("--jobs", type=int, default=18)
    ap.add_argument("--uploads", type=int, default=16)
    ap.add_argument("--total", type=float, default=9.6e6)
    ap.add_argument("--gb", type=float, default=221.5)
    ap.add_argument("--uplink-mbps", type=float, default=350)
    ap.add_argument("--resolve-ms", type=float, default=6)
    ap.add_argument("--json")
    a = ap.parse_args()
    S3.rtt, S3.put_s, S3.handshake = a.rtt, a.put, a.handshake
    tmp = tempfile.mkdtemp(prefix="bench-publish-")
    srv = tls_server(tmp)
    env = {"R2_ACCOUNT_ID": "bench", "R2_ACCESS_KEY_ID": "AKIDBENCH", "R2_SECRET_ACCESS_KEY": "bench", "R2_BUCKET": "bench",
           "R2_ENDPOINT": f"https://127.0.0.1:{srv.server_port}"}
    old = load_before(a.before)
    import publish as new
    runs = {
        "before": rate(old, env, a.objects, a.size, tmp, "before"),
        "after, kept-alive only": rate(new, env, a.objects, a.size, tmp, "keep"),
        "after, --fresh": rate(new, env, a.objects, a.size, tmp, "fresh", fresh=True),
        f"after, --fresh --uploads {a.uploads}": rate(new, env, a.objects, a.size, tmp, "threads", fresh=True, uploads=a.uploads),
    }
    srv.shutdown()
    out = {"assumed": {k: getattr(a, k) for k in ("rtt", "put", "handshake", "size", "jobs", "uploads", "total", "gb",
                                                  "uplink_mbps", "resolve_ms")}, "before_ref": a.before, "runs": {}}
    print(f"stand-in R2 over TLS: {a.rtt * 1000:.0f} ms a round trip, {a.handshake:g} to connect, {a.put * 1000:.0f} ms to "
          f"write; {a.objects} objects of {a.size / 1000:.0f} KB; projected for {a.total / 1e6:.1f} M objects, {a.gb} GB, "
          f"{a.jobs} processes, {a.uplink_mbps:g} Mbps up, {a.resolve_ms:g} ms CPU a URL")
    print(f"{'':34} {'obj/s':>7} {'conns':>6} {'HEADs':>6} {'PUTs':>6}   {'network h':>9} {'CPU h':>6} {'uplink h':>8} {'total h':>8}")
    for name, r in runs.items():
        p = project(r["per_second"], a, overlap="uploads" in name)
        out["runs"][name] = dict(r, projected=p)
        print(f"{name:34} {r['per_second']:7.1f} {r['connections']:6} {r['HEAD']:6} {r['PUT']:6}   {p['network_h']:9.2f} "
              f"{p['cpu_h']:6.2f} {p['uplink_h']:8.2f} {p['total_h']:8.2f}")
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
