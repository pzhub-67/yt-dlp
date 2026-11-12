"""grab - yt-dlp, but you don't need the manual.

Words instead of flags, in any order:

    grab URL                 best quality video, saved as .mp4
    grab URL 720p            pick a quality
    grab URL mp3             just the audio
    grab "lofi beats"        search, pick a result, download
"""
import os
import re
import shlex
import shutil
import sys

from . import __version__

HELP = """\
grab {version} - download video or audio from almost any site

USAGE
  grab URL [words...]          words can go in any order
  grab                         no arguments: asks you what to do

WHAT YOU GET
  grab URL                     best quality video (.mp4)
  grab URL 720p                cap the quality: 360p 480p 720p 1080p 1440p 4k 8k small
  grab URL mp3                 audio only: mp3 m4a flac wav opus  (or just: audio)
  grab URL mkv                 different video container: mp4 mkv webm
  grab URL subs                subtitles only (.srt)   add a language: subs es
  grab URL info                show title, length and available qualities
  grab "some words"            search YouTube and choose a result

OPTIONS
  --to FOLDER                  where to save (default: current folder)
  --clip 1:30-2:45             download only part of the video
  --subs [LANG]                embed subtitles in the video (default: en)
  --playlist                   download the whole playlist a video belongs to
  --first N                    only the first N items of a playlist
  --browser NAME               use your login from chrome/firefox/safari/edge/brave
                               (for private, members-only or age-restricted videos)
  --show                       print the equivalent yt-dlp command and stop
  -- ...                       anything after -- is passed straight to yt-dlp

OTHER
  grab check                   test this device: is ffmpeg working, what will be limited
  grab update                  update the download engine (fixes most site errors)
  grab help | grab version

EXAMPLES
  grab https://youtu.be/dQw4w9WgXcQ
  grab https://youtu.be/dQw4w9WgXcQ mp3 --to ~/Music
  grab https://youtu.be/dQw4w9WgXcQ 1080p --clip 0:30-1:00
  grab https://youtube.com/playlist?list=... audio --first 10
"""

AUDIO_FORMATS = {"mp3", "m4a", "flac", "wav", "opus"}
VIDEO_FORMATS = {"mp4", "mkv", "webm"}
QUALITY_WORDS = {"4k": 2160, "8k": 4320, "2k": 1440, "hd": 1080, "small": 480, "best": None}
BROWSERS = {"chrome", "firefox", "safari", "edge", "brave", "opera", "vivaldi", "chromium"}
FLAGS_WITH_VALUE = {"--to": "to", "-o": "to", "--clip": "clip", "--first": "first", "--browser": "browser"}

TTY = sys.stdout.isatty()


class UsageError(Exception):
    pass


def color(code, text):
    return f"\033[{code}m{text}\033[0m" if TTY and not os.environ.get("NO_COLOR") else text


def bold(t): return color("1", t)
def dim(t): return color("2", t)
def green(t): return color("32", t)
def red(t): return color("31", t)


def looks_like_url(word):
    return "://" in word or bool(re.match(r"^[\w-]+(\.[\w-]+)+(/|$)", word))


# ---------------------------------------------------------------- parsing

def parse(argv):
    """Turn free-form words into a request dict."""
    req = dict(urls=[], mode="video", quality=None, audio_format="mp3", container="mp4",
               to=None, clip=None, first=None, browser=None, subs=None, sub_lang="en",
               playlist=False, show=False, raw=[], search=[])
    if "--" in argv:
        i = argv.index("--")
        argv, req["raw"] = argv[:i], argv[i + 1:]

    args = list(argv)
    while args:
        a = args.pop(0)
        low = a.lower()
        if "=" in a and a.split("=", 1)[0] in FLAGS_WITH_VALUE:
            a, value = a.split("=", 1)
            args.insert(0, value)
            low = a
        if low in FLAGS_WITH_VALUE:
            if not args:
                raise UsageError(f"{a} needs a value, e.g. {a} {EXAMPLE_VALUES[FLAGS_WITH_VALUE[low]]}")
            req[FLAGS_WITH_VALUE[low]] = args.pop(0)
        elif low in ("--subs", "subs", "subtitles"):
            req["subs"] = "embed" if low == "--subs" else "only"
            if args and re.fullmatch(r"[a-z]{2,3}(-[A-Za-z]{2,4})?|all", args[0]) \
                    and args[0].lower() not in AUDIO_FORMATS | VIDEO_FORMATS | {"hd"}:
                req["sub_lang"] = args.pop(0)
        elif low in ("--playlist", "playlist", "all"):
            req["playlist"] = True
        elif low in ("--show", "--dry-run"):
            req["show"] = True
        elif low in ("audio", "--audio", "music", "song"):
            req["mode"] = "audio"
        elif low in ("video", "--video"):
            req["mode"] = "video"
        elif low in ("info", "--info"):
            req["mode"] = "info"
        elif low in AUDIO_FORMATS:
            req["mode"], req["audio_format"] = "audio", low
        elif low in VIDEO_FORMATS:
            req["container"] = low
        elif low in QUALITY_WORDS:
            req["quality"] = QUALITY_WORDS[low]
        elif re.fullmatch(r"\d{3,4}p?", low):
            req["quality"] = int(low.rstrip("p"))
        elif looks_like_url(a):
            req["urls"].append(a if "://" in a else "https://" + a)
        elif a.startswith("-"):
            raise UsageError(f"Unknown option {a}. Run 'grab help' to see what's available.\n"
                             f"(To pass a raw yt-dlp option, put it after '--':  grab URL -- {a})")
        else:
            req["search"].append(a)

    if req["urls"] and req["search"]:
        raise UsageError(f"I don't understand '{' '.join(req['search'])}'. Run 'grab help' for the list of words.")
    if req["subs"] == "only" and req["mode"] != "info":
        req["mode"] = "subs"
    if req["first"] is not None:
        if not str(req["first"]).isdigit() or int(req["first"]) < 1:
            raise UsageError("--first needs a number, e.g. --first 10")
        req["playlist"] = True
    if req["clip"] and not re.fullmatch(r"[\d:.]+-[\d:.]*", req["clip"]):
        raise UsageError("--clip looks like START-END, e.g. --clip 1:30-2:45  (or 1:30- for 'to the end')")
    if req["browser"] and req["browser"].lower() not in BROWSERS:
        raise UsageError(f"--browser must be one of: {', '.join(sorted(BROWSERS))}")
    return req


EXAMPLE_VALUES = {"to": "~/Videos", "clip": "1:30-2:45", "first": "10", "browser": "chrome"}


def to_ytdlp_args(req):
    """Translate a request into real yt-dlp command-line arguments."""
    a = []
    mode = req["mode"]
    if not req.get("ffmpeg", True) and mode in ("audio", "video"):
        # No ffmpeg (e.g. a-Shell on iPhone): nothing can be merged or converted,
        # so take the best file the site already offers in one piece.
        if req["clip"]:
            raise UsageError("--clip needs ffmpeg, which isn't available on this device.")
        if mode == "audio":
            a += ["-f", "ba[ext=m4a]/ba/b"]
        else:
            a += ["-f", "b", "-S", (f"res:{req['quality']}" if req["quality"] else "res") + ",ext:mp4:m4a"]
            if req["subs"] == "embed":
                a += ["--write-subs", "--write-auto-subs", "--sub-langs", req["sub_lang"]]
    elif mode == "audio":
        a += ["-f", "ba/b", "-x", "--audio-format", req["audio_format"], "--audio-quality", "0",
              "--embed-metadata"]
    elif mode == "subs":
        a += ["--skip-download", "--write-subs", "--write-auto-subs",
              "--sub-langs", req["sub_lang"], "--convert-subs", "srt"]
    elif mode == "video":
        res = f"res:{req['quality']}" if req["quality"] else "res"
        prefer = {"mp4": ",ext:mp4:m4a", "webm": ",ext:webm:webm", "mkv": ""}[req["container"]]
        a += ["-f", "bv*+ba/b", "-S", res + prefer, "--remux-video", req["container"]]
        if req["subs"] == "embed":
            a += ["--write-subs", "--write-auto-subs", "--sub-langs", req["sub_lang"], "--embed-subs"]

    if req["clip"]:
        clip = req["clip"] if not req["clip"].endswith("-") else req["clip"] + "inf"
        a += ["--download-sections", "*" + clip]
    if req["playlist"]:
        a += ["--yes-playlist"]
        if req["first"]:
            a += ["--playlist-items", f"1:{req['first']}"]
    else:
        a += ["--no-playlist"]  # a video link that happens to sit in a playlist -> just that video
    if req["browser"]:
        a += ["--cookies-from-browser", req["browser"].lower()]
    if req["to"]:
        a += ["-P", os.path.expanduser(req["to"])]
    clip = f" [clip {req['clip'].replace(':', '.').rstrip('-')}]" if req["clip"] else ""
    a += ["-o", f"%(playlist_index&{{}} - |)s%(title).150B{clip}.%(ext)s"]
    return a + req["raw"] + req["urls"]


# ---------------------------------------------------------------- output

def human_size(n):
    if not n:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def human_time(s):
    if s is None:
        return "?"
    s = int(s)
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def pretty_path(path):
    rel = os.path.relpath(path)
    return path if rel.startswith("..") else rel


class Progress:
    """One quiet, readable line per file instead of yt-dlp's wall of text."""

    def __init__(self, stage=None, dest=None):
        self.stage, self.dest = stage, dest
        self.title = None
        self.saved = []
        self.line_open = False

    def _write(self, text):
        if TTY:
            width = shutil.get_terminal_size().columns - 1
            sys.stdout.write("\r\033[K" + text[:width + 20])
            sys.stdout.flush()
            self.line_open = True

    def end_line(self):
        if self.line_open:
            sys.stdout.write("\r\033[K")
            self.line_open = False

    def say(self, text):
        self.end_line()
        print(text)

    def download_hook(self, d):
        info = d.get("info_dict") or {}
        title = info.get("title")
        if title and title != self.title:
            self.title = title
            extra = human_time(info.get("duration")) if info.get("duration") else ""
            self.say(bold(title) + (dim(f"  ({extra})") if extra else ""))
        if d["status"] == "downloading":
            done = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                frac = min(done / total, 1)
                bar = "█" * int(frac * 24) + "░" * (24 - int(frac * 24))
                speed = f"{human_size(d.get('speed'))}/s" if d.get("speed") else ""
                eta = f"{human_time(d.get('eta'))} left" if d.get("eta") is not None else ""
                self._write(f"  {bar} {frac:4.0%}  {human_size(total)}  {dim(speed + '  ' + eta)}")
            else:
                self._write(f"  downloading… {human_size(done)}")

    def post_hook(self, d):
        names = {"ExtractAudio": "converting audio", "VideoRemuxer": "finishing video", "Merger": "joining video + audio",
                 "FFmpegSubtitlesConvertor": "converting subtitles", "EmbedSubtitle": "adding subtitles"}
        if d["status"] == "started" and d["postprocessor"] in names:
            self._write(f"  {names[d['postprocessor']]}…")
        if d["status"] == "finished" and d["postprocessor"] == "MoveFiles":
            path = (d.get("info_dict") or {}).get("filepath")
            if path and self.stage and os.path.exists(path):
                final = os.path.join(self.dest, os.path.basename(path))
                if os.path.exists(final):
                    os.remove(final)
                shutil.move(path, final)
                path = final
            if path and path not in self.saved:
                self.saved.append(path)
                self.say(f"  {green('✓')} saved  {pretty_path(path)}")


class QuietLogger:
    def __init__(self, progress):
        self.progress, self.warnings = progress, []

    def debug(self, msg):
        m = re.match(r"\[info\] Writing video subtitles to: (.+)", msg)
        if m:
            self.progress.say(f"  {green('✓')} subtitles  {m.group(1)}")
        elif "has already been downloaded" in msg:
            self.progress.say(f"  {green('✓')} already downloaded, skipped")

    info = debug

    def warning(self, msg):
        self.warnings.append(msg)

    def error(self, msg):
        # yt-dlp keeps going after a failed playlist item; say why, in plain language
        self.progress.end_line()
        print(red("✗ ") + explain(msg), file=sys.stderr)


FRIENDLY = [
    (r"HTTP Error 404", "Nothing found at that link (404). Check it for typos."),
    (r"Unable to connect to proxy|Tunnel connection failed",
     "Couldn't reach the site: your network's proxy/firewall blocked the connection."),
    (r"Sign in to confirm|age[- ]restricted|members-only|Private video|login required|Use --cookies",
     "This video needs you to be logged in.\n  Try: add  --browser chrome  (or firefox/safari/edge) to use your browser's login."),
    (r"Unsupported URL", "That link isn't from a site I know how to download from."),
    (r"is not a valid URL", "That doesn't look like a link."),
    (r"Video unavailable|This video is not available|removed|deleted",
     "This video isn't available (removed, private, or blocked in your region)."),
    (r"HTTP Error 429|Too Many Requests", "The site is rate-limiting you. Wait a few minutes and try again."),
    (r"HTTP Error 403", "The site refused the download.\n  Try: grab update   (sites change often and the engine needs to keep up)"),
    (r"ffmpeg|ffprobe", "ffmpeg is needed for this and wasn't found.\n  Install it: https://ffmpeg.org/download.html  (brew install ffmpeg / apt install ffmpeg / winget install ffmpeg)"),
    (r"Unable to download|getaddrinfo|timed out|Connection|urlopen error|ProxyError|Tunnel",
     "Couldn't reach the site. Check your internet connection (or firewall/proxy) and try again."),
    (r"Requested format is not available", "That quality/format isn't available for this video. Run with 'info' to see what is."),
    (r"no subtitles|There are no subtitles", "This video has no subtitles in that language."),
]


def explain(err):
    text = re.sub(r"^ERROR:\s*", "", str(err))
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    for pattern, friendly in FRIENDLY:
        if re.search(pattern, text, re.I):
            return f"{friendly}\n  {dim('details: ' + text.splitlines()[0][:200])}"
    return text + "\n  If this keeps happening, try: grab update"


# ---------------------------------------------------------------- actions

def ffmpeg_version():
    """Return ffmpeg's version string, or None if it can't be run.

    Runs it rather than looking on PATH: on a-Shell (iPhone) ffmpeg is built into
    the shell, so there is no file to find but running it still works.
    """
    import subprocess
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    m = re.search(r"ffmpeg version (\S+)", (r.stdout or "") + (r.stderr or ""))
    return m.group(1) if m else "found"


def do_check():
    """grab check: is everything this device needs in place?"""
    import platform
    import yt_dlp.version
    ok, no = green("✓"), red("✗")
    print(f"  {ok} Python {platform.python_version()}")
    print(f"  {ok} download engine (yt-dlp {yt_dlp.version.__version__})")
    v = ffmpeg_version()
    if v:
        print(f"  {ok} ffmpeg {v}  - full quality, mp3 conversion and --clip all work")
    else:
        print(f"  {no} ffmpeg not found - downloads still work, but only ready-made files:\n"
              "      video often capped at 360-720p, audio stays m4a, no --clip, no mp3/mkv conversion.\n"
              "      Install it:\n"
              "        Android (Termux)   pkg install ffmpeg\n"
              "        Mac                brew install ffmpeg\n"
              "        Linux              sudo apt install ffmpeg\n"
              "        Windows            winget install ffmpeg\n"
              "        iPhone (a-Shell)   built in: type  ffmpeg -version  to confirm, and update a-Shell\n"
              "                           from the App Store if that fails")
    here = os.getcwd()
    print(f"  {ok if os.access(here, os.W_OK) else no} saving to {here}")
    return 0


def need_ffmpeg(req):
    if req["ffmpeg"] or req["mode"] not in ("audio", "video"):
        return
    print(dim("note: no ffmpeg on this device, so I'm taking the best ready-made file "
              "(video is often capped at 360-720p; audio stays in its original format). Run 'grab check' for how to fix."), file=sys.stderr)


def make_ydl(args, progress=None, **extra):
    import yt_dlp
    opts = yt_dlp.parse_options(args).ydl_opts
    opts.update(quiet=True, no_warnings=True, noprogress=True, **extra)
    opts["logger"] = QuietLogger(progress or Progress())
    if progress:
        opts["progress_hooks"] = [progress.download_hook]
        opts["postprocessor_hooks"] = [progress.post_hook]
    return yt_dlp.YoutubeDL(opts)


def do_download(req):
    need_ffmpeg(req)
    args = to_ytdlp_args(req)
    stage = dest = None
    if req["ffmpeg"] and (req["mode"] == "audio" or (req["mode"] == "video" and req["container"] != "mp4")):
        # Converting deletes its source file. Work in a side folder so a file you already
        # have with the same name (e.g. the video, when you now ask for the mp3) is never touched.
        dest = os.path.abspath(os.path.expanduser(req["to"] or "."))
        stage = os.path.join(dest, ".grab-partial")
        args = ["-P", stage] + [x for i, x in enumerate(args) if x != "-P" and (i == 0 or args[i - 1] != "-P")]
    progress = Progress(stage, dest)
    try:
        with make_ydl(args, progress) as ydl:
            code = ydl.download(req["urls"])
    finally:
        progress.end_line()
        if stage and os.path.isdir(stage):
            for name in os.listdir(stage):  # keep only resumable partial downloads
                if not name.endswith((".part", ".ytdl")):
                    os.remove(os.path.join(stage, name))
            if not os.listdir(stage):
                os.rmdir(stage)
    if not progress.saved and not code and req["mode"] != "subs":
        print(dim("Nothing new to download."))
    return code


def do_info(req):
    args = to_ytdlp_args(dict(req, mode="video"))
    with make_ydl(args, extract_flat="in_playlist", ignoreerrors=False) as ydl:
        for url in req["urls"]:
            info = ydl.sanitize_info(ydl.extract_info(url, download=False))
            if info.get("_type") == "playlist":
                entries = info.get("entries") or []
                print(bold(info.get("title") or url) + dim(f"  (playlist, {len(entries)} items)"))
                for i, e in enumerate(entries[:20], 1):
                    print(f"  {i:>3}. {e.get('title') or e.get('url')}  {dim(human_time(e.get('duration')))}")
                if len(entries) > 20:
                    print(dim(f"       … and {len(entries) - 20} more"))
                continue
            print(bold(info.get("title") or url))
            for label, key in (("by", "uploader"), ("uploaded", "upload_date"), ("views", "view_count")):
                if info.get(key) is not None:
                    v = info[key]
                    if key == "upload_date":
                        v = f"{v[:4]}-{v[4:6]}-{v[6:]}"
                    elif key == "view_count":
                        v = f"{v:,}"
                    print(f"  {label + ':':<10} {v}")
            print(f"  {'length:':<10} {human_time(info.get('duration'))}")
            heights = {}
            for f in info.get("formats") or []:
                h = f.get("height")
                if h and f.get("vcodec") not in (None, "none"):
                    size = f.get("filesize") or f.get("filesize_approx") or 0
                    heights[h] = max(heights.get(h, 0), size)
            if heights:
                print("  qualities: " + "  ".join(
                    f"{h}p" + (dim(f" (~{human_size(s)})") if s else "") for h, s in sorted(heights.items(), reverse=True)))
            langs = sorted(info.get("subtitles") or {})
            auto = "en" in (info.get("automatic_captions") or {})
            if langs or auto:
                print("  subtitles: " + (", ".join(langs[:15]) or "auto-generated only")
                      + (" …" if len(langs) > 15 else ""))
    return 0


def do_search(req):
    query = " ".join(req["search"])
    print(dim(f"Searching YouTube for “{query}”…"))
    with make_ydl(["--flat-playlist"], ignoreerrors=False) as ydl:
        results = (ydl.extract_info(f"ytsearch6:{query}", download=False) or {}).get("entries") or []
    if not results:
        print("No results.")
        return 1
    for i, e in enumerate(results, 1):
        who = e.get("channel") or e.get("uploader") or ""
        print(f"  {bold(str(i))}. {e.get('title')}  {dim(human_time(e.get('duration')) + '  ' + who)}")
    choice = "1"
    if sys.stdin.isatty():
        choice = input(f"Which one? [1-{len(results)}, Enter = 1, q = cancel] ").strip().lower() or "1"
    if not choice.isdigit() or not 1 <= int(choice) <= len(results):
        print("Cancelled.")
        return 0
    req["urls"] = [results[int(choice) - 1]["url"]]
    req["search"] = []
    return dispatch(req)


def do_update():
    import subprocess
    print("Updating the download engine (yt-dlp)…")
    return subprocess.call([sys.executable, "-m", "pip", "install", "-U", "--quiet", "yt-dlp"])


def wizard():
    """No arguments: just ask."""
    print(bold("grab") + dim("  - paste a link or type what to search for (Ctrl+C to quit)"))
    what = input("Link or search: ").strip()
    if not what:
        return 0
    words = [what] if looks_like_url(what) else what.split()
    kind = input("Video or audio? [V/a] ").strip().lower()
    if kind.startswith("a"):
        words.append("mp3")
    else:
        q = input("Quality? [Enter = best, or 1080, 720, 480…] ").strip().lower()
        if q:
            words.append(q)
    where = input("Save to folder? [Enter = here] ").strip()
    if where:
        words += ["--to", where]
    return dispatch(parse(words))


def dispatch(req):
    if req["search"]:
        if req["show"]:
            raise UsageError("--show needs a link, not a search.")
        return do_search(req)
    if not req["urls"]:
        raise UsageError("Give me a link or something to search for. Example:  grab https://youtu.be/dQw4w9WgXcQ")
    req.setdefault("ffmpeg", bool(ffmpeg_version()))
    if req["show"]:
        print("yt-dlp " + " ".join(shlex.quote(x) for x in to_ytdlp_args(req)))
        return 0
    return do_info(req) if req["mode"] == "info" else do_download(req)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        first = argv[0].lower() if argv else ""
        if first in ("help", "-h", "--help"):
            print(HELP.format(version=__version__))
            return 0
        if first in ("version", "--version", "-v"):
            import yt_dlp.version
            print(f"grab {__version__} (engine: yt-dlp {yt_dlp.version.__version__})")
            return 0
        if first in ("check", "doctor") and len(argv) == 1:
            return do_check()
        if first == "update" and len(argv) == 1:
            return do_update()
        if not argv:
            if sys.stdin.isatty():
                return wizard()
            print(HELP.format(version=__version__))
            return 0
        return dispatch(parse(argv))
    except UsageError as e:
        print(red("✗ ") + str(e), file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return 130
    except Exception as e:  # yt-dlp DownloadError and friends
        if os.environ.get("GRAB_DEBUG"):
            raise
        if TTY:
            sys.stdout.write("\r\033[K")
        import yt_dlp.utils
        if not isinstance(e, yt_dlp.utils.DownloadError):  # those were already explained by the logger
            print(red("✗ ") + explain(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
