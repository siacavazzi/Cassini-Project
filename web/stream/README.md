# The stream rig: ambient mode, live, ten years ago

Streams Cassini OS in ambient mode (`/?ambient=live`: the clock is today minus ten years, so the stream reaches the
Grand Finale on 15 September 2027) from the Mac Mini, 24/7.

How it works: one headless Chrome draws the page at 1280x720; the DevTools screencast hands every new frame (JPEG) to
`stream.mjs`, which feeds the newest one to ffmpeg 30 times a second; ffmpeg encodes H.264 on the Mac's hardware
encoder (`h264_videotoolbox`, not the CPU cores) with silent AAC audio and sends it to YouTube, a local HLS folder, a
file, or several at once. Nothing is re-rendered: the stream is exactly what the page draws, pictures included.

| file | what it does |
|---|---|
| `stream.mjs` | Chrome + screencast + ffmpeg, a watchdog, and one line of stats a minute (Node 22+, no npm packages) |
| `run.sh` | runs `stream.mjs` at low priority and restarts it whenever it stops on its own |
| `report.mjs` | summarizes `stats.jsonl`: frame rates, CPU in cores, memory, restarts |
| `player.html` | private test viewer for the HLS output (copied next to the playlist) |
| `com.cassini.stream.plist` | optional launchd job, to start the stream at login and after a reboot |

## Running it on the Mini

```sh
cd ~/dev/Cassini-Project
tmux new -d -s stream 'STREAM_URL="http://127.0.0.1:8765/?ambient=live" web/stream/run.sh --out ~/server/stream/hls/live.m3u8'
node web/stream/report.mjs ~/server/stream/stats.jsonl      # how it is doing
tmux kill-session -t stream                                   # stop
```

Logs, `stats.jsonl` and Chrome's own profile live in `STREAM_STATE` (default `~/server/stream`). The HLS folder holds a
rolling minute of video and an `index.html` that plays it; serve that folder (for example on a preview port) to watch
the stream privately before anything is public.

### Priority ("reserve a core")

macOS has no way to pin a program to a core. What it can do is lower a program's QoS class, and that turned out to be
the wrong lever: measured on the Mini (27 Oct, five 150 s runs of the live ambient page), any clamp slows the page's
own animation, not just its share of the CPU.

| run | priority | size | page draws | frames to ffmpeg | new frames in a 20 s clip | CPU, cores |
|---|---|---|---|---|---|---|
| A | utility | 1080p | 22 fps | 10 fps | 182 of 600 | 0.48 |
| B | normal | 1080p | 60 fps | 29 fps | 275 of 600 | 1.11 |
| C | utility | 1080p, JPEG q60 | 21 fps | 10 fps | 188 of 600 | 0.51 |
| D | utility | 720p | 14 fps | 7 fps | 45 of 600 | 0.22 |
| E | normal | 720p, q70 | 60 fps | 28 fps | 291 of 600 | 0.52 |

So the defaults are E's: normal priority, 1280x720 at 3 Mbps, JPEG quality 70, about half a core and 1.7 to 2 GB of
memory. That half core is the "reserved core": the stream simply always gets it. (A slowly drifting scene repeats
some frames on its own, so even a perfect capture shows fewer than 600 new frames in 20 s.) `STREAM_PRIORITY=utility`
(utility QoS, nice 10) or `background` (`taskpolicy -b`, nice 20; 3 to 8 frames a second under a full pre-build)
give the CPU back at the cost of a choppy stream. ffmpeg is held to 2 threads and Chrome to one renderer process.
Below 3 GB of available memory (`--min-free-gb`) the stream stops and tries again ten minutes later; so does ten
minutes in a row at under half of real time.

Note that the pre-build pauses itself while the load average is over 30, and every running program adds to the load,
so while the pre-build runs flat out, the stream slows it a little.

### Options (`stream.mjs`, passed through `run.sh`)

| option | default | |
|---|---|---|
| `--url` | `http://127.0.0.1:8765/?ambient=live` | any Cassini OS link; `run.sh` takes it from `STREAM_URL` |
| `--out` | (required, repeatable) | `youtube`, an `rtmp://`/`rtmps://` URL, a `.m3u8` path (HLS) or a `.mp4`/`.mkv` file |
| `--width`, `--height`, `--fps` | 1280, 720, 30 | the page is drawn at this size; 1080p costs twice the CPU for little gain |
| `--bitrate` | `3M` | YouTube suggests 2.5 to 6 Mbps for 720p30 (4.5 to 9 for 1080p) |
| `--quality` | 70 | JPEG quality of the screencast frames |
| `--encoder` | `h264_videotoolbox` on a Mac | `libx264` elsewhere (cloud tests) |
| `--settings` | | Cassini OS settings as JSON, merged into the page's saved settings, e.g. `'{"ambient.fps":24}'` |
| `--audio` | `silence` | or a music file, looped (it must be cleared for YouTube's Content ID) |
| `--duration` | 0 (forever) | seconds; for a test clip |
| `--stall` | 90 | restart when the page sends no frame for this long |
| `--reload-hours` | 0 (never) | reload the page every N hours, if a long soak shows memory growing |
| `--min-free-gb` | 3 | step aside when the Mini runs short of memory |

## Going live on YouTube

Only Sam can do these, and nothing goes public until he does:

1. In YouTube Studio, **Create > Go live > Stream**. YouTube asks for phone verification once and then makes you wait
   up to 24 hours before the first live stream.
2. Create a stream key with **Stream latency: normal** (lowest cost to the Mini) and copy it.
3. Put the key in a file only the Mini's user can read, never in a chat, a commit or a command line:
   `mkdir -p ~/.config/cassini-stream && pbpaste > ~/.config/cassini-stream/youtube.key && chmod 600 ~/.config/cassini-stream/youtube.key`
   (or set `YOUTUBE_STREAM_KEY` in the tmux session). `stream.mjs` masks the key in every log line.
4. Start it with `--out youtube` (add `--out ~/server/stream/hls/live.m3u8` to keep the private monitor):
   `tmux new -d -s stream 'web/stream/run.sh --out youtube --out ~/server/stream/hls/live.m3u8'`
5. In YouTube Studio, set the title, description (credit "NASA/JPL-Caltech/SSI"; no NASA logo), category Science &
   Technology, and leave DVR on. YouTube archives only the last 12 hours of a
   continuous stream, so an endless stream has no replay beyond that.

The stream sends silence as its audio track (YouTube expects one). Music needs a license that survives Content ID.
