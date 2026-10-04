# Floor plans from a phone: the plain guide

This guide is for someone who has never used a terminal. It says what the tool does, how
to run it in four steps, how to read what comes out, and how good the numbers are. The
engineering detail is in the technical report (`docs/technical_report.md`).

## 1. What it does, in one paragraph

You walk through a home with an iPhone. The tool turns what the phone recorded into a
**floor plan with measurements**: every room's shape, the length of each wall, the floor
area, the ceiling height, and the doors. It also looks for **damage** on the walls and
ceiling (holes, cracks, stains, mould, peeling paint, exposed wiring), measures how big
each damaged patch is, warns about damage that may be hidden behind it, and writes a
**repair list**. Every number comes with a range, for example "wall 4.53 m, between
4.40 and 4.66 m", so you can see how sure the tool is. We aim for the true value to lie
inside that range 9 times out of 10.

## 2. What the phone has to record (pick one)

| What you give it | Phone needed | How good |
|---|---|---|
| **LiDAR scan** (the free *Stray Scanner* app) | iPhone Pro or iPad Pro (they have a depth sensor) | Best: walls within about 5 cm |
| **Video**: one short clip per room, at eye level | Any iPhone 15 or newer | Good: walls within about 8 cm |
| **Photos**: 2 to 15 per room, one folder per room | Any iPhone 15 or newer | Rough: walls within about 20 cm |

How to film or photograph a room, step by step: `docs/capture_protocol.md` (two pages).
For damage: stand about 1 metre from it and hold the phone still for 3 seconds (video or
scan), or take one close photo and put it in that room's folder.

## 3. Running it: four steps

You type (or paste) each line below into the **Terminal** app and press Return.
To open Terminal: press Cmd + Space, type `Terminal`, press Return.

**Step 1. Go to the project folder** (once per Terminal window). Type `cd ` (with the
space), drag the project folder from Finder into the Terminal window, press Return.

**Step 2. Install everything** (once per computer, about 15 minutes, needs internet):

```
./setup.sh
```

**Step 3. Put the capture on the Mac.** AirDrop the Stray Scanner folder, the video file
or the photo folders to the Mac. Photos: make one folder per room (named after the room,
e.g. `Kitchen`), all inside one folder (e.g. `MyHome`).

**Step 4. Run it** (one line per capture). Type `./run.sh `, then drag the capture (folder
or video file) onto the window, then add ` --damage` and press Return:

```
./run.sh ~/Downloads/MyScan --damage
```

When it finishes, the floor plan picture opens by itself. Everything is saved in the
`outputs` folder, in a folder named after the capture.

**How long it takes:** a LiDAR scan takes under a minute. Video and photos need a large
AI model. The tool sends the images to Kaggle (a free online computer with a strong
graphics card), which takes about 10 minutes. With no internet it runs the model on this
Mac instead: slower (20 to 40 minutes), but it splits the work into small pieces so the
Mac never runs out of memory. Damage detection asks Google's Gemini model over the
internet, and uses a small model on the Mac when there is no internet.

## 4. Reading the results

Each capture gets a folder in `outputs/` with:

- **plan.png**: the floor plan picture. Each room is a coloured shape with its name, floor
  area and ceiling height. Every wall is labelled with its length, e.g. `4.53 ± 0.13 m`:
  the wall is 4.53 m long and the true length is very likely between 4.40 and 4.66 m. A
  dotted wall was never seen by the phone, so its length is a guess with a wide range.
- **plan.json**: the same numbers in a file other software can read (field list in
  README.md), plus every damage item, warning flag and repair line.
- **damage/**: the photos the damage model looked at, with each damage outlined.
- The text printed at the end lists **warnings**: anything the tool was unsure about, for
  example "this room had only 3 photos", is said there, never hidden.

## 5. How good is it? (tested on a real home)

A friend's home was measured three ways: by our tool, by the Polycam app (a popular paid
scanning app), and by hand with a tape and the architect's drawing (the "truth").

![LiDAR floor plan of the test home](img/plan_lidar.png)

| Check | Result |
|---|---|
| Room sizes, LiDAR scan | Typically **5 cm** off; Polycam is 6 cm off on the same rooms |
| Our scan vs Polycam, room by room | Ours as good or better on **6 of 8** measurements (target 70%) |
| Ceiling height, LiDAR | Within **1 to 2 cm** |
| Room sizes, video | Typically 8 cm off; 11 of 16 within 3% |
| Room sizes, photos | Typically 19 cm off; 29 of 40 within 8% |
| Are the ranges honest? | The truth was inside the range for 91% of LiDAR walls, 92% video, 80% photos |
| A staged hole (6.35 cm across) | Found on every input type; its measured size range held the true size **7 times out of 7** |

## 6. What it does not do well (yet)

- **Doors** are found but measured about 34 cm too narrow; **windows** are not found.
- **Photos**: each room is measured on its own, but the rooms are not joined into one
  connected plan; they are laid side by side.
- **Two scans of the same room** differ by up to 5 cm on one wall (the target is 1 cm).
- A wall the phone never saw (dotted) can be quite wrong; the range says so.
- **Damage**: grubby hand marks on white walls are reported as water stains, and ceiling
  light fittings are sometimes reported as holes.

## 7. Words used in the reports

| Word | Meaning |
|---|---|
| Tier | Which kind of input: LiDAR scan, video, or photos |
| LiDAR | The depth sensor on Pro iPhones; it measures distances directly |
| Interval / range / ± | Where the true value very likely lies (9 times out of 10) |
| Ground truth | The tape-measured or architect-drawn real size, used as the answer key |
| Drift | A scan slowly going out of position as you walk; can bend long walls |
| Reconstruction model | The AI that works out 3D shape from ordinary photos or video |
| Kaggle | A free online service with powerful computers, used to run that AI quickly |
| Gemini | Google's AI model, used to spot damage in pictures |
| Flag | A warning that damage you can see may mean damage you cannot see (e.g. a ceiling stain may mean a leak above) |
| Scope | The repair list: what to fix, on which wall, how much (e.g. square metres) |
