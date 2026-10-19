import sys, time, urllib.request, concurrent.futures as cf
urls = [l.strip() for l in open('urls.txt') if l.strip().endswith('.IMG')][:int(sys.argv[2])]
def get(u): return len(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "curl/8.7.1"}), timeout=120).read())
for p in map(int, sys.argv[1].split(',')):
    t = time.time()
    with cf.ThreadPoolExecutor(p) as ex: b = sum(ex.map(get, urls))
    dt = time.time() - t
    print(f'parallel={p} files={len(urls)} bytes={b} sec={dt:.1f} MB/s={b/dt/1e6:.2f}', flush=True)
