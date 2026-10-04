# Openings (doors and passages)

`src/floorplan/openings.py`, run by `lidar.build_plan` for every tier; output in
`rooms[].openings[]` and `adjacency[]`.

## Method

Each wall is unrolled into an elevation (along the wall x height) from the points within
−0.25 / +0.35 m of its measured face (the face plus its drift smear, fix 09). A 5 cm column
is open when under 10% of its 5 cm cells between 0.3 and 1.8 m hold points. A run of open
columns 0.6–3.0 m wide is an opening only if the scan saw through it: ≥ 30 points
0.4–4 m behind the wall at body height or on the floor. An unscanned stretch of wall is
empty too but has nothing behind it, so it is not reported. With wall above the gap (below
ceiling − 0.15 m) it is a **door**, its height the 5th percentile of those points; open to
the ceiling it is a **passage**. `connects_to` is the room found 0.4–0.9 m past the centre;
each connected room pair gets one `adjacency` entry.

**Windows are not detected.** On home C's LiDAR the window wall returns points across the
glass (grilles, frame, deep reveal), so a window leaves no gap in the elevation. Detecting
them needs the recess (surfaces behind the face) or images; not done.

## Against the ground truth (home C, friend's tape)

| Opening | Truth | `c_damage_01` | `c_damage_02` |
|---|---|---|---|
| Bedroom door, width | 1.04 m (3.4 ft) | 0.70 m (−34 cm) | 0.70 m (−34 cm) |
| Bedroom door, height | 1.98 m (6.5 ft) | 2.09 m (+11 cm) | 2.19 m (+21 cm) |
| Bedroom window | 2.13 × 1.73 m | not detected | not detected |

The door is found in both scans, consistently 34 cm narrow: the open door leaf and the
frame stand inside the band at body height (the friend's 3.4 ft is likely the frame's
outer width; unconfirmed). **Gate G1 (≤ 2 cm on ≥ 85% of openings) is not met.**

On `c_home_01` the hall↔drawing room (1.2 m door) and hall↔bedroom (0.6 m door) links are
found, so the whole-home plan now has adjacency. The hall also gets passages along its
west side, where the wall was never scanned (fix map 01c) and the floor beyond was seen:
possibly real openings (the entry gate and the hallway entry are on that side), not checked.
