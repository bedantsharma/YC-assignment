# Capture protocol

How to capture a home so our pipeline can turn it into a measured floor plan. Written for
someone who has never done this before: follow the steps in order, exactly as written.

There are three ways to capture (**tiers**). You only need the one you were asked for.

| Tier | Phone | App | Time |
|---|---|---|---|
| **LiDAR** | iPhone 12 Pro or newer **Pro** model | Stray Scanner (free, App Store) | 3–5 min per floor |
| **Video** | any iPhone 15 or newer | built-in Camera | about 1–2 min per room |
| **Photos** | any iPhone 15 or newer | built-in Camera | about 2 min per room |

## 1. Before you start (2 minutes)

1. Phone battery at **80% or more**, and at least **5 GB** of free storage.
2. Turn **on every light** in the rooms you will capture. Open the curtains and blinds.
3. **Open every door** you will walk through, and leave it open. Don't open or close any
   door once you have started.
4. If there is a **large mirror** you can easily cover (a towel works), cover it.
5. Ask people and pets to stay out of the rooms while you capture.

## 2. The walk (LiDAR tier; the Video tier differs, see below)

Hold the phone **upright in both hands at chest height**. Move **slowly**, about half your
normal walking speed. When you change direction, **turn your whole body**, not just the
phone.

1. Start in the **hallway or entrance**. Start recording, then **hold still for 3 seconds**
   pointing at something with detail (a picture, a shelf, a door frame).
2. Walk into the first room. Go around it **keeping the wall on your left**, with the phone
   pointed **across the room** at the opposite wall.
3. In **every room**, before you leave it:
   - **Every wall, top to bottom:** sweep each wall from the floor up to where it meets the
     ceiling, including the parts behind and above furniture. A wall the phone never sees
     is measured wrong (on our test home, one unseen wall cost 23 cm).
   - **Ceiling:** tilt the phone up until you can see where the walls meet the ceiling, and
     turn slowly in a full circle.
   - **Floor:** tilt down until you can see where the walls meet the floor, and turn slowly in
     a full circle.
   - **Doors and windows:** stand about 2 m from each one, face it straight on so the whole
     frame is in view, and **hold for 2 seconds**.
   - **Damage** (cracks, stains, mould, holes): go to about 1 m away, face it, **hold for
     3 seconds**.
4. Walk through a doorway into the next room and repeat steps 2–3. Visit every room once.
5. **Finish where you started.** Point at the same thing as in step 1, **hold still for
   3 seconds**, then stop recording.

Keep each recording **under 5 minutes** and to **one floor**. For a bigger home, make one
recording per floor.

**LiDAR tier:** open **Stray Scanner**, tap the record button, do the walk, tap stop.

### Video tier: one short clip per room

Open **Camera**, choose **Video**, check the lens is **1x** (not 0.5x), and check **Action
mode is off** (the running-figure icon is not highlighted). Do not use Cinematic mode.

Record **one clip per room**, about 1–2 minutes each (a long clip of the whole home came
out with rooms folded onto each other; clips of one room were within 5 cm):

1. Stand in the doorway, start recording, hold still for 3 seconds.
2. Walk slowly around the room, phone **at eye level** pointed across the room at the
   opposite wall, so each shot shows the floor line, the whole wall and the ceiling line.
   Tilt up or down only a little; no full circles at the ceiling or the floor.
3. Damage: go to about 1 m away, face it, **hold for 3 seconds**.
4. Back at the doorway, hold still for 3 seconds, stop.

If you are asked for the whole home in **one** video, do the same at eye level through
every room, under 5 minutes, without ceiling or floor circles.

## 3. Photos tier

Settings: **Camera > Photo**, lens **1x**, hold the phone **sideways (landscape)**, no zoom,
no Portrait mode, flash off. **RAW / ProRAW off** (Settings > Camera > Formats): the
pipeline reads normal photos (HEIC or JPEG), not RAW files.

**First, make one album per room** in the Photos app (tap **+**, then **New Album**), named
`Room 1 Kitchen`, `Room 2 Hallway`, and so on. After each room, add its photos to its album.

In **each room**, take about **15 photos** (minimum 4) in this order:

| Photos | Where to stand | Where to point |
|---|---|---|
| 4 | In each **corner** | At the opposite corner |
| 4 | With your back to the middle of each **wall** | At the opposite wall, whole wall in view |
| 1 each | 2 m in front of each **door and window** | Straight at it, whole frame in view |
| 1 each | In each **doorway** | **Into the next room** (this is how rooms get joined) |
| 1 each | 1 m from any **damage** (put it in that room's folder) | Straight at it |
| 2 | The **middle** of the room | Into any areas the other photos missed |

In every photo, make sure you can see **where the walls meet the floor** and, where
possible, **where they meet the ceiling**. Neighbouring photos should share about half of
what they show. Don't move furniture between photos.

If you are short of time, the 4 corner photos plus the doorway photos are the minimum. Fewer
photos still work, but the measurements will be less precise.

## 4. Handing over the files

AirDrop everything to the laptop running the pipeline.

- **LiDAR:** in Stray Scanner, open the recording, tap **Share**, choose the laptop.
- **Video:** in Photos, select the video, tap **Share > Options**, switch on **All Photos
  Data**, then AirDrop it.
- **Photos:** open each room album, tap **Select > Select All > Share > Options**, switch on
  **All Photos Data**, then AirDrop it. Do **one album at a time** and tell the operator
  which room it is: AirDrop delivers loose photos, and the operator puts each room's photos
  in a folder named after the room.

Do **not** send files through WhatsApp or email: they shrink photos and videos and lose the
information the pipeline needs.

## 5. Avoid

| Avoid | Why |
|---|---|
| Moving fast or spinning on the spot | The phone loses track of where it is, and the plan comes out bent |
| People or pets moving through the shot | They appear as walls or furniture that isn't there |
| Opening or closing doors mid-capture | The phone sees a moving wall |
| Pointing at a mirror or glass wall for long | They reflect or pass the light, so the phone sees rooms that don't exist |
| Dim rooms (darker than a living room at night) or strong direct sunlight | Tracking fails and LiDAR misses surfaces |
| 0.5x lens, zoom, Portrait, Cinematic or Action mode | They crop or bend the image, so measurements come out wrong |

## For the operator (pipeline side)

One command per capture, on whatever AirDrop delivered (a Stray Scanner zip or folder, a
video file, or a folder with one subfolder per room):

```
./run.sh <capture> --damage
```

Step by step, with what to do when something fails: [walkin_runbook.md](walkin_runbook.md).

## Known limits

- **Mirrors, glass walls, wet or shiny floors:** depth readings are unreliable there. The
  pipeline flags these areas with a warning and widens the intervals.
- **Low light** (below about 50 lux): tracking and LiDAR coverage degrade.
- **Very large open spaces** (wider than about 9 m) and **open-plan layouts**: room
  boundaries are harder to find.
- **Multi-storey homes:** one recording per floor; floors are not joined automatically.
