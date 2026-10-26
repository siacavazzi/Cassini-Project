# The stream rig: ambient mode, live, ten years ago

Streams Cassini OS in ambient mode (`/?ambient=live`: the clock is today minus ten years, so the stream reaches the
Grand Finale on 15 September 2027) from the Mac Mini, 24/7.

How it works: one headless Chrome draws the page at 1920x1080; the DevTools screencast hands every new frame (JPEG) to
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

macOS has no way to pin a program to a core. Instead `run.sh` runs the whole rig (Chrome, ffmpeg, the script) at
background QoS (`taskpolicy -b`, which keeps it mostly on the efficiency cores and throttles its disk use) and nice 20,
so the pre-build and the servers always come first and the stream gets what is left. `STREAM_PRIORITY=utility` is a
step up if the stream stutters while the Mini has room; `normal` removes the clamp. ffmpeg is held to 2 threads and
Chrome to one renderer process. Below 3 GB of available memory (`--min-free-gb`) the stream stops and tries again ten
minutes later.

### Options (`stream.mjs`, passed through `run.sh`)

| option | default | |
|---|---|---|
| `--url` | `http://127.0.0.1:8765/?ambient=live` | any Cassini OS link; `run.sh` takes it from `STREAM_URL` |
| `--out` | (required, repeatable) | `youtube`, an `rtmp://`/`rtmps://` URL, a `.m3u8` path (HLS) or a `.mp4`/`.mkv` file |
| `--width`, `--height`, `--fps` | 1920, 1080, 30 | the page is drawn at this size; ambient mode caps its own 3D at 30 fps |
| `--bitrate` | `6M` | YouTube suggests 4.5 to 9 Mbps for 1080p30 |
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
