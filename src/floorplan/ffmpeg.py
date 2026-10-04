"""Where ffmpeg comes from, and what the video tier asks ffprobe, without needing ffprobe.

ffmpeg: the system one if installed (e.g. Homebrew), else the binary that the
`imageio-ffmpeg` package ships (part of `uv sync --extra video`), so a Mac without Homebrew
needs nothing else. That package has no ffprobe, so the two facts we read with it (length
and rotation tag) fall back to the file itself: the length from the MP4 / MOV headers,
the rotation from what `ffmpeg -i` prints.

Checked against ffprobe on every video we have (Oct 4): the 10 iPhone videos (Camera app,
Stray Scanner) give the same length to the microsecond and the same rotation; ARKitScenes'
multi-track .mov files differ by 5-12 ms (tracks offset by empty edits), which the video
tier does not use. The bundled ffmpeg 7.1 decodes pixel-identical frames to Homebrew's 7.1.1,
so cached reconstructions (keyed by pixels) replay either way.
"""

import json
import re
import shutil
import struct
import subprocess
from functools import cache
from pathlib import Path


@cache
def exe() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
    except ImportError as err:
        raise RuntimeError(
            "the video tier needs ffmpeg: run `uv sync --extra video` (bundles one) "
            "or install it (e.g. `brew install ffmpeg`)"
        ) from err
    return imageio_ffmpeg.get_ffmpeg_exe()


def duration(video: Path) -> float:
    if shutil.which("ffprobe"):
        out = _probe(video, ["-show_entries", "format=duration"])
        return float(out["format"]["duration"])
    exact = _mp4_duration(video)
    if exact is not None:
        return exact
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", _info(video))
    if not m:
        raise RuntimeError(f"ffmpeg could not read the length of {video}")
    h, mi, s = m.groups()
    return 3600 * int(h) + 60 * int(mi) + float(s)


def has_rotation(video: Path) -> bool:
    """True if the first video stream carries a rotation (tag or display matrix)."""
    if shutil.which("ffprobe"):
        out = _probe(
            video,
            ["-select_streams", "v:0", "-show_entries",
             "stream_side_data=rotation:stream_tags=rotate"],
        )  # fmt: skip
        stream = out["streams"][0]
        return bool(stream.get("tags", {}).get("rotate")) or any(
            "rotation" in d for d in stream.get("side_data_list", [])
        )
    text = _info(video)
    return bool(re.search(r"\brotate\s*:\s*-?\d", text) or "rotation of" in text)


def _mp4_duration(video: Path) -> float | None:
    """Length of an MP4 / MOV file the way ffprobe reports it: the longest track, from each
    track's edit list ('elst', in the movie's timescale) or else its media header
    ('mdhd'), rounded to the 6 decimals ffprobe
    prints. `ffmpeg -i` prints it rounded to 10 ms, and the movie header ('mvhd') can differ
    in the last digits; either would move the sampled frame times. None if not MP4 / MOV."""

    def boxes(f, end):
        while f.tell() + 8 <= end:
            start = f.tell()
            size, kind = struct.unpack(">I4s", f.read(8))
            if size == 1:
                size = struct.unpack(">Q", f.read(8))[0]
            elif size == 0:
                size = end - start
            if size < 8:
                return
            yield kind, f.tell(), start + size
            f.seek(start + size)

    def find(f, body, end, path):
        f.seek(body)
        for kind, b, e in list(boxes(f, end)):
            if kind == path[0]:
                yield from ([(b, e)] if len(path) == 1 else find(f, b, e, path[1:]))

    def header(f, body):
        """(timescale, duration) of an mvhd / mdhd box (same layout up to there)."""
        f.seek(body)
        if f.read(4)[0] == 1:
            _, _, scale, length = struct.unpack(">QQIQ", f.read(28))
        else:
            _, _, scale, length = struct.unpack(">IIII", f.read(16))
        return scale, length

    try:
        with open(video, "rb") as f:
            total = f.seek(0, 2)
            mvhd = next(find(f, 0, total, [b"moov", b"mvhd"]), None)
            if mvhd is None:
                return None
            movie_scale, _ = header(f, mvhd[0])
            lengths = []
            for tbody, tend in list(find(f, 0, total, [b"moov", b"trak"])):
                track = []
                mdhd = next(find(f, tbody, tend, [b"mdia", b"mdhd"]), None)
                if mdhd is not None:
                    scale, length = header(f, mdhd[0])
                    if scale:
                        track.append(length / scale)
                elst = next(find(f, tbody, tend, [b"edts", b"elst"]), None)
                if elst is not None and movie_scale:  # edit list: the presented length
                    f.seek(elst[0])
                    version = f.read(4)[0]
                    (n,) = struct.unpack(">I", f.read(4))
                    fmt, size = (">QqHH", 20) if version == 1 else (">IiHH", 12)
                    segs = [struct.unpack(fmt, f.read(size))[0] for _ in range(n)]
                    track.append(sum(segs) / movie_scale)
                if track:  # the shorter of the two, as ffprobe reports a trimmed track
                    lengths.append(min(track))
    except (OSError, struct.error, IndexError):
        return None
    return round(max(lengths), 6) if lengths else None


def _probe(video: Path, args: list[str]) -> dict:
    cmd = ["ffprobe", "-v", "error", *args, "-of", "json", str(video)]
    return json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)


def _info(video: Path) -> str:
    """What `ffmpeg -i` prints about the file (it exits non-zero: no output was asked for)."""
    return subprocess.run([exe(), "-hide_banner", "-i", str(video)], capture_output=True,
                          text=True).stderr  # fmt: skip
