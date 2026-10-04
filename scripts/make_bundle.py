"""Build the raw-data bundle for submission: outputs/bundle/*.zip + SHA256SUMS + MANIFEST.md.

Each zip unpacks at the repo root into the paths the code reads, so after
`scripts/fetch_data.sh` the repo is as on our laptop:

- floorplan_home_c_raw.zip: home C (the friend's home, owner's permission to submit):
  LiDAR recordings (Stray Scanner), Camera-app videos, photos per room, the photo sets
  and video stills derived from them, Polycam screenshots with the street address blacked
  out. Ground truth is in git (data/gt/). The architect's drawing photo is not included
  (address and stamp); its numbers are in data/gt/home_c.json.
- floorplan_replay_cache.zip: the Kaggle model outputs that scripts/reproduce.sh replays
  (video, photo-sim and real-photo reconstructions), so no GPU is needed.

Not included: Cozmo's captures (dataset A, theirs) and ARKitScenes (dataset B, public:
scripts/fetch_arkitscenes.sh).

    uv run scripts/make_bundle.py
"""

import hashlib
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path("outputs/bundle")
RAW = [
    "data/home_c/lidar",
    "data/home_c/video",
    "data/home_c/photos",
    "data/home_c/photo_sets",
    "data/home_c/photos_sim",
]
CACHE = [
    "outputs/kaggle_video_runs/recon_cache",
    "outputs/kaggle_cache_runs/recon_cache",
    "outputs/recon_cache_photos",
]
# street address line on the Polycam plan screenshots (pixels), checked by eye on Oct 5
ADDRESS = {"floorplan_a": (393, 640, 813, 676), "floorplan_b": (200, 313, 390, 332)}
POLYCAM = Path("data/home_c/polycam")


def files(roots: list[str]) -> list[Path]:
    out = []
    for r in roots:
        out += sorted(p for p in Path(r).rglob("*") if p.is_file() and not p.name.startswith("."))
    return out


def polycam(stage: Path) -> list[tuple[Path, str]]:
    stage.mkdir(parents=True, exist_ok=True)
    out = []
    for src in sorted(POLYCAM.glob("*.jpeg")):
        im = Image.open(src).convert("RGB")
        box = ADDRESS.get(src.stem)
        if box:
            ImageDraw.Draw(im).rectangle(box, fill="black")
        dst = stage / f"{src.stem}.jpg"
        im.save(dst, quality=92)
        out.append((dst, f"data/home_c/polycam/{dst.name}"))
    return out


def write_zip(name: str, entries: list[tuple[Path, str]]) -> Path:
    path = OUT / name
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for src, arc in entries:
            z.write(src, arc)
    tmp.rename(path)
    return path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = [(p, str(p)) for p in files(RAW)] + polycam(OUT / "stage")
    cache = [(p, str(p)) for p in files(CACHE)]
    zips = [write_zip("floorplan_home_c_raw.zip", raw),
            write_zip("floorplan_replay_cache.zip", cache)]  # fmt: skip
    sums = {z.name: sha256(z) for z in zips}
    (OUT / "SHA256SUMS").write_text("".join(f"{h}  {n}\n" for n, h in sums.items()))
    lines = ["# Raw-data bundle", "", "| File | Size | Files | SHA-256 |", "|---|---|---|---|"]
    for z, entries in zip(zips, (raw, cache), strict=True):
        lines.append(f"| {z.name} | {z.stat().st_size / 1e9:.2f} GB | {len(entries)} | "
                     f"`{sums[z.name][:16]}…` |")  # fmt: skip
    lines += ["", "Contents by folder:", ""]
    for roots in (RAW + ["data/home_c/polycam"], CACHE):
        for r in roots:
            sel = [e for e in raw + cache if e[1].startswith(r + "/")]
            size = sum(s.stat().st_size for s, _ in sel)
            lines.append(f"- `{r}/`: {len(sel)} files, {size / 1e6:.0f} MB")
    (OUT / "MANIFEST.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
