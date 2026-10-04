"""A stand-in for the model in the local worker's child process (tests only, never in src/).

Same command line as `python -m floorplan.mvs_local --worker <in> <out> <model>`, but writes
random points that depend only on each frame's pixels, so shared frames chain exactly.
A window of more than KILL_ABOVE frames kills the process (SIGKILL), as the OS does to a
process that runs the machine out of memory.
"""

import hashlib
import os
import signal
import sys

import numpy as np

KILL_ABOVE = 6
GRID = (28, 37)

if __name__ == "__main__":
    src, dst = sys.argv[2], sys.argv[3]
    z = np.load(src)
    frames = [z[k] for k in sorted(z.files, key=lambda k: int(k[4:]))]
    if len(frames) > KILL_ABOVE:
        os.kill(os.getpid(), signal.SIGKILL)
    pts = []
    for f in frames:
        seed = int(hashlib.sha1(f.tobytes()).hexdigest()[:15], 16)
        pts.append(np.random.default_rng(seed).normal(0, 2, (*GRID, 3)).astype(np.float32))
    pts = np.stack(pts)
    np.savez(dst, view_points=pts, view_keep=np.ones(pts.shape[:3], bool),
             cam_poses=np.tile(np.eye(4), (len(frames), 1, 1)), seconds=0.0)  # fmt: skip
