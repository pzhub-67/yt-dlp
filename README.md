# grab

yt-dlp, but you don't need the manual. Same engine and same supported sites
(it runs yt-dlp under the hood) with plain words instead of flags.

## Install

```bash
pip install -e .
```

Needs Python 3.9+ and [ffmpeg](https://ffmpeg.org/download.html).

## Use

| You want | Type | yt-dlp equivalent |
|---|---|---|
| The video | `grab URL` | `yt-dlp -f "bv*+ba/b" -S res,ext:mp4:m4a --remux-video mp4 --no-playlist URL` |
| 720p | `grab URL 720p` | `... -S res:720,ext:mp4:m4a ...` |
| An mp3 | `grab URL mp3` | `yt-dlp -f ba/b -x --audio-format mp3 --audio-quality 0 --embed-metadata URL` |
| Part of it | `grab URL --clip 1:30-2:45` | `--download-sections "*1:30-2:45"` |
| Subtitles | `grab URL subs es` | `--skip-download --write-subs --write-auto-subs --sub-langs es --convert-subs srt` |
| What's available | `grab URL info` | `yt-dlp -F URL` |
| A whole playlist | `grab URL --playlist` / `--first 10` | `--yes-playlist --playlist-items 1:10` |
| A login-only video | `grab URL --browser chrome` | `--cookies-from-browser chrome` |
| To search | `grab "lofi beats" mp3` | `yt-dlp "ytsearch:..."` |
| To be asked | `grab` | n/a |

Words go in any order. `grab help` lists everything.

Nothing is lost: anything after `--` goes straight to yt-dlp
(`grab URL -- --limit-rate 1M`), and `--show` prints the exact yt-dlp command
instead of running it.

## ffmpeg

ffmpeg does the merging and converting. Run `grab check` to see whether it works on your device.

| With ffmpeg | Without |
|---|---|
| Best quality (up to 4K/8K) | Best single ready-made file, often 360-720p |
| mp3 / flac / wav / opus | Audio in its original format (usually m4a) |
| mkv / webm, `--clip`, `--subs` built in | Not available |

Install: `pkg install ffmpeg` (Termux), `brew install ffmpeg` (Mac), `sudo apt install ffmpeg` (Linux),
`winget install ffmpeg` (Windows). a-Shell on iPhone has it built in.

## Web pages

- `builder.html` - pick options and copy the matching `grab` command.
- `watch.html` - paste a YouTube link and watch it embedded. Needs a web address (GitHub Pages or `python -m http.server`), not a local file.

## Test

```bash
pip install pytest && python -m pytest
```
