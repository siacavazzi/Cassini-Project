# python's http.server with a listen backlog of 128 (the stock 5 resets connections when a page asks many files at once)
import functools, http.server, sys
port, root = int(sys.argv[1]), sys.argv[2]
class S(http.server.ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True
S(("0.0.0.0", port), functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)).serve_forever()
