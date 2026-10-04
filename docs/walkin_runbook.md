# Walk-in runbook

The defense: Cozmo captures a space we have never seen with their iPhone, at a tier they
choose on the day, following our protocol; our pipeline runs on it cold on this laptop
while they laser-measure the space. This page is what to do, in order, and what to do when
something goes wrong.

## The night before

- [ ] `git pull` and `uv sync --extra video --extra offline` in the repo.
- [ ] `uv run floorplan check`: every line OK (Kaggle, Gemini, Florence-2, ffmpeg, disk).
- [ ] Laptop charged, charger packed; phone hotspot ready (Kaggle and Gemini need network).
- [ ] At least 5 GB free on the disk (`floorplan check` says).
- [ ] Print or have open: [capture_protocol.md](capture_protocol.md) as a PDF (two pages; they
      follow it literally): `uv run scripts/md_to_pdf.py docs/capture_protocol.md`.

## On arrival (5 minutes)

1. Open Terminal, go to the repo (`cd ` then drag the folder in), run:
   ```
   uv run floorplan check
   ```
   All four tiers must say `ready`. If Kaggle or Gemini fails, switch to the phone hotspot
   and run it again.
2. Hand them the protocol. Point out three things: walk slowly, sweep every wall up to the
   ceiling, and hold the phone still for 3 seconds about 1 m from any damage.
3. Ask them to AirDrop the result to this laptop (it lands in `~/Downloads`).

## Running their capture (one command)

| They captured | What arrives | Command |
|---|---|---|
| LiDAR (Stray Scanner) | a zip (or a folder) | `./run.sh ~/Downloads/<recording>.zip --damage` |
| Video, one clip per room (what the protocol asks) | one `IMG_xxxx.MOV` per room | per clip: `./run.sh ~/Downloads/IMG_xxxx.MOV --frames 60 --damage` |
| Video, one clip of several rooms | `IMG_xxxx.MOV` | `./run.sh ~/Downloads/IMG_xxxx.MOV --frames 90 --damage` (long whole-home clips can fold rooms together: ask for one clip per room if there is time) |
| Photos | loose photos | in Finder make `~/Downloads/walkin/<RoomName>/` per room and drag each room's photos in, then `./run.sh ~/Downloads/walkin --damage` |

The plan picture opens by itself when it is done. Results: `outputs/<name>_<tier>/`
(`plan.png`, `plan.json`, `damage/` with the outlined frames).

Expected time: LiDAR under a minute (+1-2 min with damage). Video and photos: ~5 min
(uploads to Kaggle, GPU job, download), printed as it goes: `Kaggle: uploading…`, `GPU job
started`, `done in N min`. Use the wait to explain the method.

## Reading the result out

- Each wall: `4.53 ± 0.13 m` = estimate and 90% range; dotted walls were not seen.
- Each room: floor area and ceiling height with ranges.
- The printed **warnings** are part of the answer: say them (e.g. "3 photos in this room,
  interval widened", "ceiling not captured").
- Compare against their laser numbers as they read them; note which are inside our range.

## When something goes wrong

| Symptom | What to do |
|---|---|
| `Kaggle not used (...)` and the run tries to work locally | Network: switch to the hotspot, Ctrl-C, run the same command again. This laptop cannot run the model itself (16 GB); say so. |
| Kaggle job takes > 10 min | Kaggle is queuing. Keep it running; meanwhile run their LiDAR capture if there is one. Hard cap: `FLOORPLAN_KAGGLE_TIMEOUT_MIN` (default 40). |
| The damage warning names `florence-2-base` instead of Gemini | Gemini was unreachable, so damage ran offline (weaker; finds close-ups). The plan is unaffected. |
| `no room found` | Too little of the room seen. Video: rerun with `--frames 90`. Photos: ask for more (the protocol's ~15 per room). LiDAR: ask for a slower second sweep of the walls. |
| Plan looks rotated / walls tilted on a video | Orientation guess wrong: rerun with `--up top` (or `right` / `left`). |
| `not a recognised capture` | Wrong path, or the zip holds something else: open it in Finder, pass the folder that contains `odometry.csv` (LiDAR) or the room folders (photos). |
| Run crashes | Note the last line, rerun once; fall back to another tier they captured. |

## What to say while it runs

- One geometry backend for every tier: LiDAR depth, or Pi3X from video / photos, becomes the
  same metric point cloud; the same code finds floor, ceiling, walls and rooms.
- Ranges are honest: 91% of LiDAR walls and 92% of video walls had the truth inside the
  90% range on our test home; thin input gives wider ranges, not confident wrong numbers.
- The fix loop: walls were 29 cm short (drift smear + furniture), now 5 cm; as good as
  Polycam on what was scanned (6 of 8 dimensions beat or tie).
- Known limits, before they find them: doors come out narrow, windows are not detected,
  photo rooms are not stitched into one plan, hand grime reads as water stain.
- Decisions and their evidence: [decisions.md](decisions.md).

## Rehearsal (still to do, needs a person and an iPhone)

On a room none of our data has seen: someone follows the protocol at each tier, AirDrops,
and the commands above run cold. Tape two walls and the ceiling to score it. Record the
times and anything that went wrong here.
