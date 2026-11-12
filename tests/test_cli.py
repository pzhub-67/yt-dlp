import pytest

from grab.cli import UsageError, parse, to_ytdlp_args

U = "https://youtu.be/abc"


def args(*words):
    return to_ytdlp_args(parse(list(words)))


def test_default_is_best_mp4_single_video():
    a = args(U)
    assert a[:6] == ["-f", "bv*+ba/b", "-S", "res,ext:mp4:m4a", "--remux-video", "mp4"]
    assert "--no-playlist" in a and a[-1] == U


def test_words_in_any_order():
    assert args("720p", U) == args(U, "720") == args(U, "720P")
    assert "res:720,ext:mp4:m4a" in args(U, "720p")
    assert "res:2160,ext:mp4:m4a" in args(U, "4k")


def test_audio():
    a = args(U, "flac")
    assert a[a.index("--audio-format") + 1] == "flac" and "-x" in a
    assert args(U, "audio")[args(U, "audio").index("--audio-format") + 1] == "mp3"


def test_subs():
    a = args(U, "subs", "es")
    assert "--skip-download" in a and a[a.index("--sub-langs") + 1] == "es"
    b = args(U, "--subs", "mkv")
    assert "--embed-subs" in b and b[b.index("--sub-langs") + 1] == "en" and "mkv" in b


def test_options():
    a = args(U, "--clip", "1:30-2:45", "--first=3", "--to", "/tmp/x", "--browser", "Chrome")
    assert a[a.index("--download-sections") + 1] == "*1:30-2:45"
    assert a[a.index("--playlist-items") + 1] == "1:3" and "--yes-playlist" in a
    assert a[a.index("-P") + 1] == "/tmp/x"
    assert a[a.index("--cookies-from-browser") + 1] == "chrome"
    assert "*1:30-inf" in args(U, "--clip", "1:30-")


def test_raw_passthrough_and_bare_domain():
    a = args("youtu.be/abc", "--", "--limit-rate", "1M")
    assert a[-3:] == ["--limit-rate", "1M", "https://youtu.be/abc"]


def test_search_words():
    assert parse(["lofi", "beats", "mp3"])["search"] == ["lofi", "beats"]


@pytest.mark.parametrize("bad", [[U, "--wat"], [U, "nonsense"], [U, "--clip", "abc"],
                                 [U, "--first", "x"], [U, "--to"], [U, "--browser", "netscape"]])
def test_bad_input_is_explained(bad):
    with pytest.raises(UsageError):
        parse(bad)


def test_generated_args_are_valid_ytdlp():
    import yt_dlp
    for words in ([U], [U, "mp3"], [U, "subs"], [U, "--subs", "1080p", "mkv", "--clip", "0:10-0:20"],
                  [U, "webm", "--first", "2", "--browser", "firefox"]):
        yt_dlp.parse_options(args(*words))
