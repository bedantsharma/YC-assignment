"""Damage detection on images: a hosted VLM (Gemini) finds and labels damage as boxes, a
model-free step outlines each box as a pixel mask (docs/damage_research.md).

Detector. One Gemini call per image asks for the five damage classes plus two context
classes (sockets / switches and exposed wiring, used only by the concealed-damage rules).
Boxes come back as `box_2d` = [ymin, xmin, ymax, xmax] normalised to 0-1000.

Credentials are never read or stored by this code: `google-genai` picks them up from the
environment. Vertex AI: `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`,
`GOOGLE_CLOUD_LOCATION` and either `GOOGLE_APPLICATION_CREDENTIALS` (service-account JSON)
or `gcloud auth application-default login`; or Vertex express mode / the Gemini Developer
API with `GOOGLE_API_KEY`. Model: `FLOORPLAN_GEMINI_MODEL` (default `DEFAULT_MODEL`).

Detector. `FLOORPLAN_DAMAGE_DETECTOR`: `auto` (default), `gemini` or `florence`. In `auto`,
cached Gemini answers are used first; the first Gemini call that fails (no network, no
credentials) switches the rest of the run to Florence-2-base on the laptop
(damage_local.py), and `fallback_reason` says why. The crack pass is Gemini only.

Cache. A hosted model cannot be rerun to the same answer later, so every response is stored
as JSON in `FLOORPLAN_DAMAGE_CACHE` (default `data/damage_cache`), keyed by the image bytes
sent, the model and the prompt version. `FLOORPLAN_DAMAGE_CACHE_ONLY=1` makes a miss an error:
reported numbers then replay without the network.

Crack pass (optional, `crack_pass=True`). Boxes suit cracks badly and the main prompt
misses faint ones, so a second call per image asks only for cracks, traced as polylines;
the mask is the polyline CRACK_PX wide, and its length comes straight from the trace.

Mask. Inside each box (padded), pixels that differ from the ring of wall around it by more
than a robust threshold; the connected part nearest the box centre is kept. When that finds
too little or almost the whole box, the ellipse inscribed in the box is used instead and
the mask is marked `ellipse`.
"""

import contextlib
import hashlib
import io
import json
import os
import random
import threading
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

DAMAGE_CLASSES = ("crack", "water_stain", "mould", "hole", "peeling_paint")
CONTEXT_CLASSES = ("outlet_or_switch", "exposed_wiring")
DEFAULT_MODEL = "gemini-3.1-pro-preview"  # cleanest of 2.5 Flash, 3.8 Flash, 3.1 Pro on IMG_1371
MODEL_ENV = "FLOORPLAN_GEMINI_MODEL"
DETECTOR_ENV = "FLOORPLAN_DAMAGE_DETECTOR"
CACHE_ENV = "FLOORPLAN_DAMAGE_CACHE"
CACHE_ONLY_ENV = "FLOORPLAN_DAMAGE_CACHE_ONLY"
DEFAULT_CACHE = Path("data/damage_cache")
PROMPT_VERSION = "v1"
SEND_LONG_SIDE = 1536  # px; boxes are normalised, so the size only limits detail and cost
JPEG_QUALITY = 92
MIN_SCORE = 0.3
RETRIES = 3  # rate limit / overload: wait RETRY_S, 2x, 4x (+ jitter) before giving up
RETRY_S = 4.0
_lock = threading.Lock()

PROMPT = f"""You are a building surveyor inspecting the interior surfaces (walls, ceiling,
floor) of a home in this photo for damage.

Find every visible instance of these damage classes:
- crack: a crack in plaster, drywall or paint (not a joint between boards or tiles)
- water_stain: a water or damp stain, tide mark or discolouration from moisture
- mould: mould or mildew growth (dark speckled patches)
- hole: a hole or missing piece in a wall, ceiling or floor surface
- peeling_paint: paint that is peeling, flaking or blistering

Also mark these context objects (they are not damage):
- outlet_or_switch: an electrical socket, switch plate or junction box on a surface
- exposed_wiring: visible electrical wires or conduit on or coming out of a surface

Do NOT report furniture, decor, shadows, reflections, light spots, wood grain, picture
hooks, small nail holes (under 5 mm), or the normal edges where two surfaces meet.
One box per separate instance; a box tight around that instance only.

Answer with a JSON list (empty list if there is nothing). Each item has:
"label": one of {", ".join(DAMAGE_CLASSES + CONTEXT_CLASSES)};
"box_2d": [ymin, xmin, ymax, xmax] normalised to 0-1000;
"confidence": 0 to 1, how sure you are this is a real instance of that class;
"note": a few words on what you see."""

CRACK_PROMPT_VERSION = "crack-v1"
CRACK_PROMPT = """You are a building surveyor looking ONLY for cracks in the interior
surfaces (plaster, drywall, paint) of a home in this photo. Look closely: include faint
hairline cracks, short cracks, and cracks radiating from corners, holes, sockets or
patched areas.

Do NOT report: joints between boards, tiles or panels; the edges of furniture, frames,
doors or windows; the corner line where two surfaces meet; wires, cables or strings;
shadows, scratches on furniture, wood grain; or the outline of a smooth plaster patch
(a filled repair) unless the patch itself is cracked.

Answer with a JSON list (empty list if there are no cracks). Each item has:
"points": the crack traced as a polyline, a list of 2 to 20 [y, x] points normalised to
0-1000, in order along the crack, following its bends;
"confidence": 0 to 1, how sure you are this is a real crack;
"note": a few words (e.g. "hairline crack from hole towards ceiling")."""
MAX_CRACKS = 15  # more traced cracks in one image = the model looping (seen: 54 on a clean wall)
CRACK_PX = 3  # width of a traced crack's mask: hairlines are thinner than this anyway

RING_FRAC = 0.25  # ring of background around a box, as a share of the box size
BOX_PAD_FRAC = 0.1  # boxes from VLMs are loose: search a little outside them
MIN_MAD = 6.0  # grey levels: floor on the background spread
THRESH_SIGMA = 3.0
MASK_MIN_FILL, MASK_MAX_FILL = 0.03, 0.9  # share of the box; outside: use the ellipse


@dataclass
class Detection:
    image_id: str
    label: str
    score: float
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 in pixels of the image given
    note: str = ""
    mask: np.ndarray | None = field(default=None, repr=False)  # bool, full image size
    mask_source: str = ""  # "contrast", "ellipse" or "polyline"
    points: list[tuple[float, float]] | None = None  # crack pass: traced (x, y) pixels
    source: str = "main"  # which prompt found it: "main" or "crack"

    @property
    def is_damage(self) -> bool:
        return self.label in DAMAGE_CLASSES


fallback_reason: str | None = None  # set when auto mode switched to the local model


def gemini_model() -> str:
    return os.environ.get(MODEL_ENV, DEFAULT_MODEL)


def _local() -> bool:
    mode = os.environ.get(DETECTOR_ENV, "auto")
    if mode not in ("auto", "gemini", "florence"):
        raise ValueError(f"{DETECTOR_ENV} must be auto, gemini or florence, got {mode!r}")
    return mode == "florence" or (mode == "auto" and fallback_reason is not None)


def model_name() -> str:
    """The detector in use (after any fallback)."""
    from floorplan import damage_local

    return damage_local.NAME if _local() else gemini_model()


def detect(
    image_id: str, image: Image.Image, with_masks: bool = True, crack_pass: bool = False
) -> list[Detection]:
    """Damage and context detections on one upright image. crack_pass: a second call that
    traces cracks as polylines; its cracks replace the main prompt's cracks they overlap."""
    data = _encode(image)
    items = _cached_call(data, PROMPT, PROMPT_VERSION)
    w, h = image.size
    dets = []
    for item in parse_items(items):
        y0, x0, y1, x1 = item["box_2d"]
        box = (x0 / 1000 * w, y0 / 1000 * h, x1 / 1000 * w, y1 / 1000 * h)
        det = Detection(image_id, item["label"], item["confidence"], box, item["note"])
        if det.score < MIN_SCORE:
            continue
        if with_masks:
            det.mask, det.mask_source = outline(image, box)
        dets.append(det)
    if crack_pass:
        cracks = []
        traced = parse_crack_items(_cached_call(data, CRACK_PROMPT, CRACK_PROMPT_VERSION))
        if len(traced) > MAX_CRACKS:
            warnings.warn(
                f"{image_id}: crack pass returned {len(traced)} cracks; discarded as degenerate",
                stacklevel=2,
            )
            traced = []
        for item in traced:
            if item["confidence"] < MIN_SCORE:
                continue
            pts = [(x / 1000 * w, y / 1000 * h) for y, x in item["points"]]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            box = (min(xs), min(ys), max(xs), max(ys))
            det = Detection(image_id, "crack", item["confidence"], box, item["note"])
            det.points, det.source = pts, "crack"
            if with_masks:
                det.mask, det.mask_source = polyline_mask(pts, (w, h)), "polyline"
            cracks.append(det)
        dets = [
            d
            for d in dets
            if d.label != "crack" or not any(_boxes_touch(d.box, c.box) for c in cracks)
        ] + cracks
    return dets


def parse_crack_items(items) -> list[dict]:
    """Keep polylines of 2+ in-range points."""
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not isinstance(it.get("points"), list):
            continue
        pts = []
        for p in it["points"]:
            if isinstance(p, list | tuple) and len(p) == 2:
                with contextlib.suppress(TypeError, ValueError):
                    pts.append(tuple(min(1000.0, max(0.0, float(v))) for v in p))
        if len(pts) < 2:
            continue
        try:
            score = min(1.0, max(0.0, float(it.get("confidence", 0.5))))
        except (TypeError, ValueError):
            continue
        out.append({"points": pts, "confidence": score, "note": str(it.get("note", ""))[:200]})
    return out


def polyline_mask(points: list[tuple[float, float]], size: tuple[int, int]) -> np.ndarray:
    im = Image.new("1", size, 0)
    ImageDraw.Draw(im).line(points, fill=1, width=CRACK_PX, joint="curve")
    # not np.asarray(im, dtype=bool): a mode-"1" image gives a read-only array whose True
    # bytes are 255, which skeletonize (crack length) rejects or crashes on
    return np.asarray(im, dtype=np.uint8) > 0


def _boxes_touch(a, b) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def parse_items(items) -> list[dict]:
    """Keep well-formed items with a known label; clip boxes to 0-1000 and order them."""
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        label = str(it.get("label", "")).strip().lower().replace(" ", "_")
        label = {"mold": "mould", "peeling": "peeling_paint", "stain": "water_stain"}.get(
            label, label
        )
        box = it.get("box_2d")
        if label not in DAMAGE_CLASSES + CONTEXT_CLASSES or not isinstance(box, list):
            continue
        if len(box) != 4:
            continue
        try:
            y0, x0, y1, x1 = (min(1000.0, max(0.0, float(v))) for v in box)
            score = float(it.get("confidence", 0.5))
        except (TypeError, ValueError):
            continue
        y0, y1 = sorted((y0, y1))
        x0, x1 = sorted((x0, x1))
        if y1 - y0 < 1 or x1 - x0 < 1:
            continue
        out.append(
            {
                "label": label,
                "box_2d": [y0, x0, y1, x1],
                "confidence": min(1.0, max(0.0, score)),
                "note": str(it.get("note", ""))[:200],
            }
        )
    return out


def outline(image: Image.Image, box: tuple[float, float, float, float]):
    """Pixel mask of the damage inside `box` (model-free), and how it was made."""
    grey = np.asarray(image.convert("L"), dtype=float)
    h, w = grey.shape
    x0, y0, x1, y1 = box
    bw, bh = max(x1 - x0, 2.0), max(y1 - y0, 2.0)
    px, py = BOX_PAD_FRAC * bw, BOX_PAD_FRAC * bh
    rx, ry = RING_FRAC * bw + px, RING_FRAC * bh + py
    ox0, oy0 = int(max(0, x0 - rx)), int(max(0, y0 - ry))
    ox1, oy1 = int(min(w, x1 + rx + 1)), int(min(h, y1 + ry + 1))
    ix0, iy0 = int(max(0, x0 - px)), int(max(0, y0 - py))
    ix1, iy1 = int(min(w, x1 + px + 1)), int(min(h, y1 + py + 1))

    mask = np.zeros((h, w), bool)
    win = grey[oy0:oy1, ox0:ox1]
    inner = np.zeros(win.shape, bool)
    inner[iy0 - oy0 : iy1 - oy0, ix0 - ox0 : ix1 - ox0] = True
    ring = win[~inner]
    if ring.size >= 20 and inner.any():
        med = float(np.median(ring))
        mad = max(1.4826 * float(np.median(np.abs(ring - med))), MIN_MAD)
        odd = inner & (np.abs(win - med) > THRESH_SIGMA * mad)
        odd = ndimage.binary_closing(odd, iterations=2) & inner
        lab, n = ndimage.label(odd)
        if n:
            cy, cx = (y0 + y1) / 2 - oy0, (x0 + x1) / 2 - ox0
            sizes = ndimage.sum(odd, lab, range(1, n + 1))
            coms = np.array(ndimage.center_of_mass(odd, lab, range(1, n + 1)))
            dist = np.hypot(coms[:, 0] - cy, coms[:, 1] - cx) / np.hypot(bw, bh)
            # big parts near the centre win; tiny specks far away lose
            k = int(np.argmax(sizes / (1.0 + 4.0 * dist)))
            part = ndimage.binary_fill_holes(lab == k + 1)
            fill = part.sum() / max(1, inner.sum())
            if MASK_MIN_FILL <= fill <= MASK_MAX_FILL:
                mask[oy0:oy1, ox0:ox1] = part
                return mask, "contrast"
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    mask = ((xx + 0.5 - cx) / (bw / 2)) ** 2 + ((yy + 0.5 - cy) / (bh / 2)) ** 2 <= 1.0
    return mask, "ellipse"


def _encode(image: Image.Image) -> bytes:
    im = image.convert("RGB")
    scale = SEND_LONG_SIDE / max(im.size)
    if scale < 1:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def _cache_path(data: bytes, model: str, version: str = PROMPT_VERSION) -> Path:
    root = Path(os.environ.get(CACHE_ENV, DEFAULT_CACHE))
    key = hashlib.sha1(data + model.encode() + version.encode()).hexdigest()[:20]
    return root / f"{model}_{version}" / f"{key}.json"


def _cached_call(data: bytes, prompt: str, version: str) -> list:
    global fallback_reason
    from floorplan import damage_local

    gemini = _cache_path(data, gemini_model(), version)
    if not _local() and gemini.exists():
        return json.loads(gemini.read_text())["items"]
    if _local() or os.environ.get(DETECTOR_ENV, "auto") == "florence":
        return _local_call(data, version)
    if os.environ.get(CACHE_ONLY_ENV) == "1":
        local = _cache_path(data, damage_local.NAME, damage_local.CACHE_VERSION)
        if os.environ.get(DETECTOR_ENV, "auto") == "auto" and local.exists():
            return _local_call(data, version)  # replaying a run that fell back
        raise RuntimeError(f"damage cache miss ({gemini}) and {CACHE_ONLY_ENV}=1")
    try:
        text = _call_gemini(data, gemini_model(), prompt)
    except Exception as err:  # no network, no credentials, quota: fall back if allowed
        if os.environ.get(DETECTOR_ENV, "auto") != "auto":
            raise
        with _lock:
            if fallback_reason is None:
                fallback_reason = f"{type(err).__name__}: {str(err)[:150]}"
                warnings.warn(
                    f"Gemini unavailable ({fallback_reason}); using {damage_local.NAME} "
                    "on this laptop for the rest of the run",
                    stacklevel=2,
                )
        return _local_call(data, version)
    path, model = gemini, gemini_model()
    items = _parse_json(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "model": model,
        "prompt_version": version,
        "image_sha1": hashlib.sha1(data).hexdigest(),
        "raw": text,
        "items": items,
    }
    path.write_text(json.dumps(record, indent=1))
    return items


def _local_call(data: bytes, version: str) -> list:
    """Florence-2 answer for these image bytes (cached like Gemini's; no crack pass)."""
    from floorplan import damage_local

    if version != PROMPT_VERSION:
        return []
    path = _cache_path(data, damage_local.NAME, damage_local.CACHE_VERSION)
    if path.exists():
        return damage_local.to_items(json.loads(path.read_text())["proposals"])
    if os.environ.get(CACHE_ONLY_ENV) == "1":
        raise RuntimeError(f"damage cache miss ({path}) and {CACHE_ONLY_ENV}=1")
    with _lock:  # one model on the laptop's GPU: no parallel calls
        props = damage_local.proposals(Image.open(io.BytesIO(data)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": damage_local.NAME, "proposals": props}, indent=1))
    return damage_local.to_items(props)


def _parse_json(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1 :] if "\n" in text else text
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end <= start:
            return []
        try:
            out = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    return out if isinstance(out, list) else []


def _call_gemini(data: bytes, model: str, prompt: str) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError as err:  # pragma: no cover
        raise RuntimeError("google-genai is not installed: uv sync") from err
    client = genai.Client()
    for attempt in range(RETRIES + 1):
        try:
            return _generate(client, types, data, model, prompt)
        except Exception as err:  # rate limits and overload pass; anything else is real
            transient = any(
                k in str(err) for k in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE")
            )
            if not transient or attempt == RETRIES:
                raise
            time.sleep(RETRY_S * 2**attempt + random.uniform(0, 1))
    raise AssertionError("unreachable")


def _generate(client, types, data: bytes, model: str, prompt: str) -> str:
    response = client.models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=data, mime_type="image/jpeg"), prompt],
        config=types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    return response.text or "[]"
