"""`floorplan check`: is this machine ready for each tier, right now? (Run before the walk-in.)

Calls no paid API and downloads nothing: it checks that the pieces are present and that
the services answer on the network.
"""

import os
import shutil
import socket
from pathlib import Path

MIN_FREE_GB = 5


def run() -> int:
    rows = []  # (ok, what, detail)

    def add(ok, what, detail):
        rows.append((ok, what, detail))

    # ffmpeg (video tier)
    try:
        from floorplan import ffmpeg

        exe = ffmpeg.exe()
        where = "system" if shutil.which("ffmpeg") == exe else "bundled (imageio-ffmpeg)"
        add(True, "ffmpeg", where)
    except Exception as err:
        add(False, "ffmpeg", str(err))

    # Kaggle (video / photo model)
    try:
        from floorplan import remote

        user = remote.username()
        remote.command()
        remote._online()
        add(True, "Kaggle (video / photo model)", f"credentials for {user}, kaggle.com reachable")
    except Exception as err:
        add(False, "Kaggle (video / photo model)", str(err))

    # local model fallback (informational)
    pi3x = Path.home() / ".cache/huggingface/hub/models--yyfz233--Pi3X"
    absent = "absent: without Kaggle, video / photo runs download 5.4 GB and need ~24 GB RAM"
    add(None, "Pi3X weights on this machine", "present" if pi3x.exists() else absent)

    # Gemini (damage)
    vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")
    creds = any(os.environ.get(k) for k in ("GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"))
    host = "aiplatform.googleapis.com" if vertex else "generativelanguage.googleapis.com"
    if not creds:
        add(False, "Gemini (damage)", "no GOOGLE_API_KEY / GOOGLE_APPLICATION_CREDENTIALS in "
            "this shell (damage falls back to Florence-2)")  # fmt: skip
    else:
        add(_reachable(host), "Gemini (damage)",
            f"{'Vertex AI' if vertex else 'Gemini API'} credentials set, {host} "
            f"{'reachable' if _reachable(host) else 'NOT reachable'}")  # fmt: skip

    # Florence-2 (offline damage)
    try:
        from huggingface_hub import try_to_load_from_cache

        from floorplan.damage_local import MODEL_ID

        cached = isinstance(try_to_load_from_cache(MODEL_ID, "config.json"), str)
        add(cached, "Florence-2 (offline damage)", "weights cached" if cached else
            "not cached: `uv run python -m floorplan.damage_local --fetch`")  # fmt: skip
    except Exception as err:
        add(False, "Florence-2 (offline damage)", f"{err} (`uv sync --extra offline`)")

    free = shutil.disk_usage(".").free / 2**30
    add(free >= MIN_FREE_GB, "Disk space", f"{free:.0f} GB free (need {MIN_FREE_GB})")

    for ok, what, detail in rows:
        mark = {True: "OK  ", False: "FAIL", None: "note"}[ok]
        print(f"[{mark}] {what}: {detail}")
    status = {what: ok for ok, what, _ in rows}
    kaggle = status["Kaggle (video / photo model)"]
    gemini, florence = status["Gemini (damage)"], status["Florence-2 (offline damage)"]
    tiers = {
        "LiDAR tier": "ready" if status["Disk space"] else "NOT ready",
        "Video tier": "ready" if status["ffmpeg"] and kaggle else "NOT ready (ffmpeg, Kaggle)",
        "Photo tier": "ready" if kaggle else "NOT ready (needs Kaggle)",
        "Damage": "ready" if gemini else "offline Florence-2 only" if florence else "NOT ready",
    }
    print()
    for name, state in tiers.items():
        print(f"{name + ':':<12} {state}")
    return 0 if all(ok is not False for ok, _, _ in rows) else 1


def _reachable(host: str) -> bool:
    try:
        socket.create_connection((host, 443), timeout=5).close()
        return True
    except OSError:
        return False
