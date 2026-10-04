"""Merged damage -> output `Damage`, concealed-damage `Flag`s and repair `ScopeItem`s.

Rule ids and wording follow docs/damage_research.md §4 (sources there); scope items follow
§5 (Xactimate-style trade codes, metric units, no pricing). Rules R9 and R10 are our own
heuristics, not sourced. R6 (diagonal crack from a door / window corner) is not
implemented: openings carry no position along their wall yet.
"""

from floorplan.damage_geom import Merged
from floorplan.output import Damage, Flag, Measurement, Room, ScopeItem, Surface

BRE_STRUCTURAL_M = 0.005  # crack width above which BRE Digest 251 category >= 3
DAMP_BOTTOM_M, DAMP_TOP_M = 0.10, 1.20
MOULD_PRO_M2 = 0.93  # EPA: 10 sq ft
NEAR_MOULD_M = 0.5
NEAR_WIRING_M = 0.3
PATCH_MAX_M2 = 0.37  # 4 sq ft: larger holes need a section of board replaced
MARGIN_M = 0.15  # board cut back past the damage on each side
# value, lo, hi: a typical storey, for walls of a room whose ceiling was never seen
UNKNOWN_HEIGHT_M = (2.7, 2.2, 3.6)

RULES = {
    "R1": "Water stain on a ceiling: possible roof or plumbing leak above. Moisture-meter "
    "check advised; a past leak cannot be told from an active one",
    "R2": "Stain or peeling paint rising from skirting level (bottom <= 0.1 m, top <= 1.2 m "
    "above the floor): possible rising damp",
    "R3": "Mould: a hidden moisture source is likely (leak or condensation); fix the source "
    "before cleaning",
    "R4": "Mould over 0.93 m2 (10 sq ft, interval upper bound): professional remediation "
    "scale; growth may continue inside the wall cavity",
    "R5": "Peeling or blistering paint: possible moisture behind the finish",
    "R7": "Crack wider than 5 mm (BRE Digest 251 category 3 or more): structural movement "
    "possible; refer to a structural engineer",
    "R8": "Crack up to 5 mm wide (BRE Digest 251 category 0-2): usually aesthetic; "
    "redecorate and monitor",
    "R9": "Water stain and mould within 0.5 m on the same surface: ongoing moisture likely, "
    "not a one-off event (own rule)",
    "R10": "Crack or hole within 0.3 m of a socket, switch or wiring: possible damage to "
    "concealed wiring; electrician check advised (own rule)",
}


def surfaces(rooms: list[Room]) -> list[Surface]:
    """Every wall face, floor and ceiling with its area."""
    out = []
    for room in rooms:
        for wall in room.walls:
            # ceiling never seen: the wall still exists; its height is a wide guess
            h = room.ceiling_height or Measurement(*UNKNOWN_HEIGHT_M, "m")
            area = _product(wall.length, h)
            out.append(Surface(f"{wall.id}.face", room.id, "wall", area, wall.id))
        out.append(Surface(f"{room.id}.floor", room.id, "floor", room.floor_area))
        if room.ceiling_height:
            out.append(Surface(f"{room.id}.ceiling", room.id, "ceiling", room.floor_area))
    return out


def build(
    merged: list[Merged], rooms: list[Room]
) -> tuple[list[Surface], list[Damage], list[Flag], list[ScopeItem]]:
    surfs = surfaces(rooms)
    known = {s.id for s in surfs}
    damage_m = [m for m in merged if m.label not in ("outlet_or_switch", "exposed_wiring")]
    damage_m = [m for m in damage_m if m.surface.surface_id in known]
    context = [m for m in merged if m not in damage_m and m.surface.surface_id in known]
    damage_m.sort(key=lambda m: (m.surface.surface_id, m.label, m.centre))

    damages, by_id = [], {}
    for k, m in enumerate(damage_m, start=1):
        d = Damage(
            id=f"d{k}",
            surface_id=m.surface.surface_id,
            damage_class=m.label,
            score=round(m.score, 3),
            region=tuple(round(x, 4) for x in m.region),
            area=_m(m.area, "m2", 5),
            centre=tuple(round(x, 4) for x in m.centre),
            length=_m(m.length, "m") if m.length else None,
            width_band=_width_band(m),
            views=m.views,
            note="; ".join(m.notes)[:300],
        )
        damages.append(d)
        by_id[d.id] = m
    flags = _flags(damages, by_id, context)
    scope = _scope(damages, by_id, flags, {s.id: s for s in surfs})
    return surfs, damages, flags, scope


def _flags(damages: list[Damage], by_id: dict, context: list[Merged]) -> list[Flag]:
    fired: list[tuple[str, str, list[str]]] = []
    for d in damages:
        m = by_id[d.id]
        kind = m.surface.kind
        u0, v0, u1, v1 = d.region
        if d.damage_class == "water_stain" and kind == "ceiling":
            fired.append(("R1", d.surface_id, [d.id]))
        low = v0 <= DAMP_BOTTOM_M and v1 <= DAMP_TOP_M
        if d.damage_class in ("water_stain", "peeling_paint") and kind == "wall" and low:
            fired.append(("R2", d.surface_id, [d.id]))
        if d.damage_class == "mould":
            fired.append(("R3", d.surface_id, [d.id]))
        if d.damage_class == "peeling_paint":
            fired.append(("R5", d.surface_id, [d.id]))
        if d.damage_class == "crack" and m.width_m is not None:
            confident_wide = m.width_m - 2 * m.px_size_m > BRE_STRUCTURAL_M
            fired.append(("R7" if confident_wide else "R8", d.surface_id, [d.id]))
        if d.damage_class in ("crack", "hole"):
            near = [
                c
                for c in context
                if c.surface.surface_id == d.surface_id
                and _gap(c.region, d.region) <= NEAR_WIRING_M
            ]
            if near:
                fired.append(("R10", d.surface_id, [d.id]))
    mould = [d for d in damages if d.damage_class == "mould"]
    if mould and sum(d.area.hi for d in mould) > MOULD_PRO_M2:
        fired.append(("R4", mould[0].surface_id, [d.id for d in mould]))
    stains = [d for d in damages if d.damage_class == "water_stain"]
    for s in stains:
        for mo in mould:
            if s.surface_id == mo.surface_id and _gap(s.region, mo.region) <= NEAR_MOULD_M:
                fired.append(("R9", s.surface_id, [s.id, mo.id]))
    return [
        Flag(f"f{k}", rule, RULES[rule], surface, ids)
        for k, (rule, surface, ids) in enumerate(fired, start=1)
    ]


def _scope(
    damages: list[Damage], by_id: dict, flags: list[Flag], surfs: dict[str, Surface]
) -> list[ScopeItem]:
    items: list[tuple[str, str, Measurement, list[str]]] = []
    r4 = {i for f in flags if f.rule_id == "R4" for i in f.damage_ids}
    for d in damages:
        m = by_id[d.id]
        kind = m.surface.kind
        if d.damage_class == "crack" and d.length:
            items.append(("DRY: tape, fill and finish crack", d.surface_id, d.length, [d.id]))
        elif d.damage_class == "hole":
            if d.area.hi <= PATCH_MAX_M2:
                items.append(("DRY PATCH: drywall patch", d.surface_id, _each(), [d.id]))
            else:
                items.append(("DRY: remove and replace drywall", d.surface_id, _cut(d), [d.id]))
        elif d.damage_class == "water_stain":
            items.append(("PNT SP: seal stain with stain blocker", d.surface_id, d.area, [d.id]))
            if kind == "ceiling":
                items.append(
                    (
                        "DRY CL: remove and replace ceiling drywall if wet (moisture-meter check)",
                        d.surface_id,
                        _cut(d),
                        [d.id],
                    )
                )
        elif d.damage_class == "mould":
            items.append(("WTR GRM: apply antimicrobial agent", d.surface_id, d.area, [d.id]))
            if kind == "wall":
                items.append(
                    ("WTR DRYW: remove and replace mouldy drywall", d.surface_id, _cut(d), [d.id])
                )
            if d.id in r4:
                items.append(
                    (
                        "WTR / HMR: containment, HEPA clean and clearance test",
                        d.surface_id,
                        d.area,
                        [d.id],
                    )
                )
        elif d.damage_class == "peeling_paint":
            items.append(("PNT: scrape, prep and seal", d.surface_id, d.area, [d.id]))
    # repaint the whole face so the colour matches (own choice, docs/damage_research.md §5)
    paint: dict[str, list[str]] = {}
    for d in damages:
        if d.damage_class in ("crack", "hole", "water_stain", "peeling_paint", "mould"):
            paint.setdefault(d.surface_id, []).append(d.id)
    for sid, ids in paint.items():
        if sid in surfs and surfs[sid].kind != "floor":
            action = "PNT S/P: seal and paint whole surface, 2 coats"
            items.append((action, sid, surfs[sid].area, ids))
    return [
        ScopeItem(f"s{k}", sid, action, qty, ids)
        for k, (action, sid, qty, ids) in enumerate(items, start=1)
    ]


def _width_band(m: Merged) -> str | None:
    if m.label != "crack":
        return None
    if m.width_m is None:
        return "not measured (crack outlined from a box, not traced)"
    res = 2 * m.px_size_m  # two pixels: the narrowest width an image can show
    if m.width_m <= res:
        return f"not resolved (below {1000 * res:.1f} mm, 2 px)"
    if m.width_m - res > BRE_STRUCTURAL_M:
        return "> 5 mm (BRE category 3+)"
    return f"<= 5 mm (about {1000 * m.width_m:.1f} mm, +-{1000 * res:.1f} mm)"


def _cut(d: Damage) -> Measurement:
    """Board area cut out: damage extent plus a margin on each side."""
    u0, v0, u1, v1 = d.region
    w, h = u1 - u0 + 2 * MARGIN_M, v1 - v0 + 2 * MARGIN_M
    rel = (d.area.hi - d.area.lo) / 2 / max(d.area.value, 1e-9)
    rel = min(rel, 1.0) * 0.5  # extent errs about half as much as area, relatively
    a = w * h
    return Measurement(round(a, 4), round(a * (1 - rel), 4), round(a * (1 + rel), 4), "m2")


def _each() -> Measurement:
    return Measurement(1.0, 1.0, 1.0, "each")


def _product(a: Measurement, b: Measurement) -> Measurement:
    v = a.value * b.value
    ra = (a.hi - a.lo) / 2 / a.value if a.value else 0.0
    rb = (b.hi - b.lo) / 2 / b.value if b.value else 0.0
    half = v * (ra**2 + rb**2) ** 0.5
    return Measurement(round(v, 4), round(v - half, 4), round(v + half, 4), "m2")


def _m(t: tuple[float, float, float], unit: str, digits: int = 4) -> Measurement:
    v, lo, hi = (round(float(x), digits) for x in t)
    return Measurement(v, min(lo, v), max(hi, v), unit)


def _gap(a, b) -> float:
    """Distance between two (u0, v0, u1, v1) boxes, 0 when they overlap."""
    du = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dv = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return float((du**2 + dv**2) ** 0.5)
