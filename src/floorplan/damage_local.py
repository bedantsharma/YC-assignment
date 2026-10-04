"""Offline damage detector: Florence-2-base on the laptop, for when Gemini is unreachable
(no network or no credentials at the walk-in; Cozmo asked for a local fallback).

Florence-2-base (Microsoft, 0.23 B parameters, MIT licence), loaded through transformers'
native Florence-2 support from `florence-community/Florence-2-base`. Two stages:

1. Where: open-vocabulary detection with a few phrases (PROPOSAL_PHRASES). Tested on the
   staged room (Oct 4), Florence-2 grounds every phrase to the most salient thing in the
   image ("hole", "crack" and "black mould" all return the staged hole; a phrase with no
   match returns the whole image), so the phrase only proposes a box; near-duplicate and
   whole-image boxes are dropped.
2. What: caption a crop around each box (2x the box, `<CAPTION>`) and map words to our
   classes (KEYWORDS). A caption with no damage or context word drops the box. Crops of the
   hole and the wiring read "A hole in a wall with a bunch of wires in it" / "A white wall
   with a bunch of wires attached to it"; a blank wall and the touch grime gave no damage
   words. Whole-image captions and region descriptions were useless (the hole was an
   "invertebrate", the bedroom a "bathroom"), and small damage seen from across a room is
   missed: this is a weak fallback, scored in docs/damage_models.md.

Boxes come back in Gemini's `box_2d` format (0-1000), with confidence LOCAL_SCORE (Florence-2
gives none), so masks, sizing, the two-view rule, flags and scope are unchanged.

Weights (~0.5 GB) are fetched once by `uv run python -m floorplan.damage_local --fetch`
(needs `uv sync --extra offline`); after that the model loads from the local cache with
no network. User's rule: no models on the laptop, except Florence-2-base and SAM 2.1 tiny
for this fallback (Oct 4).
"""

import re
import sys
from functools import cache

from PIL import Image

MODEL_ID = "florence-community/Florence-2-base"
NAME = "florence-2-base"
CACHE_VERSION = "props-v1"  # cache holds boxes + captions; classes mapped on read
TASK = "<OPEN_VOCABULARY_DETECTION>"
CAPTION = "<CAPTION>"
PROPOSAL_PHRASES = ("hole", "crack", "stain", "electric wires")
KEYWORDS = {  # caption words -> class (regex, word starts only: "molding" is not mould)
    "hole": r"\bholes?\b",
    "crack": r"\bcrack",
    "water_stain": r"\bstain|\bdiscolou?r|\bwater damage|\bdamp\b",
    "mould": r"\bmou?lds?\b|\bmouldy\b|\bmoldy\b|\bmildew",
    "peeling_paint": r"\bpeel|\bflak|\bchipped|\bblister",
    "exposed_wiring": r"\bwires?\b|\bwiring\b|\bcables?\b",
    "outlet_or_switch": r"\bsockets?\b|\boutlets?\b|\bswitch|\bplugs?\b",
}
LOCAL_SCORE = 0.5
MAX_BOX_FRAC = 0.5  # a box covering half the image is the model grounding nothing
SAME_BOX = 0.7  # share of the smaller box inside the other: the same thing
CROP_PAD = 2.0  # crop = box scaled by this about its centre
INPUT_LONG_SIDE = 768  # Florence-2 resizes to 768 x 768 anyway


def detect_items(image: Image.Image) -> list[dict]:
    """Detections on one upright image, in Gemini's item format."""
    return to_items(proposals(image))


def proposals(image: Image.Image) -> list[dict]:
    """Model output for one image: boxes (0-1000, Gemini's box_2d order) with the caption
    of a crop around each. Cached as is, so the keyword map can change without a rerun."""
    im = image.convert("RGB")
    small = im.copy()
    small.thumbnail((INPUT_LONG_SIDE, INPUT_LONG_SIDE), Image.LANCZOS)
    w, h = small.size
    boxes: list[list[float]] = []
    for phrase in PROPOSAL_PHRASES:
        out = _run(small, TASK, phrase)
        for b in out.get("bboxes", []):
            x0, y0, x1, y1 = b
            if (x1 - x0) * (y1 - y0) > MAX_BOX_FRAC * w * h or x1 <= x0 or y1 <= y0:
                continue
            same = [k for k, c in enumerate(boxes) if _overlap(b, c) >= SAME_BOX]
            if not same:
                boxes.append(list(b))
            elif _area(b) < _area(boxes[same[0]]):  # nested proposals: keep the tighter
                boxes[same[0]] = list(b)
    out = []
    sx, sy = im.width / w, im.height / h
    for x0, y0, x1, y1 in boxes:
        cx, cy = (x0 + x1) / 2 * sx, (y0 + y1) / 2 * sy
        hw, hh = (x1 - x0) * sx * CROP_PAD / 2, (y1 - y0) * sy * CROP_PAD / 2
        crop = im.crop((int(max(0, cx - hw)), int(max(0, cy - hh)),
                        int(min(im.width, cx + hw)), int(min(im.height, cy + hh))))  # fmt: skip
        box = [1000 * y0 / h, 1000 * x0 / w, 1000 * y1 / h, 1000 * x1 / w]
        out.append({"box_2d": box, "caption": str(_run(crop, CAPTION))})
    return out


def to_items(props: list[dict]) -> list[dict]:
    """Classes from each crop's caption (a caption may name several; none: not damage)."""
    items = []
    for p in props:
        text = p["caption"].lower()
        for label, pattern in KEYWORDS.items():
            if re.search(pattern, text):
                items.append(
                    {"label": label, "box_2d": p["box_2d"], "confidence": LOCAL_SCORE,
                     "note": p["caption"]}
                )  # fmt: skip
    return items


def _run(image: Image.Image, task: str, text: str = ""):
    import torch

    model, processor, device = _load()
    inputs = processor(text=task + text, images=image, return_tensors="pt").to(device)
    with torch.inference_mode():
        ids = model.generate(**inputs, max_new_tokens=128, num_beams=3, do_sample=False)
    decoded = processor.batch_decode(ids, skip_special_tokens=False)[0]
    return processor.post_process_generation(decoded, task=task, image_size=image.size)[task]


def _area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _overlap(a, b) -> float:
    """Intersection over the smaller box: 1 when one box lies inside the other."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    small = min(_area(a), _area(b))
    return ix * iy / small if small > 0 else 0.0


@cache
def _load():
    import torch
    from transformers import AutoProcessor, Florence2ForConditionalGeneration

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    try:  # offline first: the walk-in may have no network
        model = Florence2ForConditionalGeneration.from_pretrained(MODEL_ID, local_files_only=True)
        processor = AutoProcessor.from_pretrained(MODEL_ID, local_files_only=True)
    except OSError as err:
        raise RuntimeError(
            f"{MODEL_ID} is not in the local cache: run "
            "`uv run python -m floorplan.damage_local --fetch` once with network"
        ) from err
    return model.to(device).eval(), processor, device


def fetch() -> None:
    from transformers import AutoProcessor, Florence2ForConditionalGeneration

    Florence2ForConditionalGeneration.from_pretrained(MODEL_ID)
    AutoProcessor.from_pretrained(MODEL_ID)
    print(f"{MODEL_ID} cached")


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch()
    else:
        img = Image.open(sys.argv[1]) if len(sys.argv) > 1 else Image.new("RGB", (64, 64))
        for item in detect_items(img):
            print(item)
