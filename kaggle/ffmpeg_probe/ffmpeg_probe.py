"""Print Kaggle's ffmpeg build (version, libraries, CPU) to match it on the laptop.

The laptop replays Kaggle's reconstructions only if both decode a video into identical
pixels; c_home_v2 decoded differently (frame hashes differ), so the versions are compared.
"""

import platform
import subprocess

print("machine:", platform.machine(), platform.platform())
for cmd in (["which", "-a", "ffmpeg"], ["ffmpeg", "-version"], ["dpkg", "-s", "ffmpeg"]):
    r = subprocess.run(cmd, capture_output=True, text=True)
    print("$", " ".join(cmd), "\n", r.stdout, r.stderr[-500:])
