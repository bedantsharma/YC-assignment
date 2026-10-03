"""Render one of our Markdown documents to a clean A4 PDF.

Supports what our docs use: headings, paragraphs, bullet and numbered lists (one nesting
level), "- [ ]" checkboxes, tables, code blocks, **bold**, *italic* and `code`.

Usage: uv run scripts/md_to_pdf.py docs/capture_protocol.md [--out x.pdf] [--skip "Section"]
"""

import argparse
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ACCENT = colors.HexColor("#1f4e79")
GRID = colors.HexColor("#c8d3df")
HEAD_BG = colors.HexColor("#eaf0f6")

TITLE = ParagraphStyle(
    "title", fontName="Helvetica-Bold", fontSize=20, leading=26, textColor=ACCENT, spaceAfter=6
)
H2 = ParagraphStyle(
    "h2",
    fontName="Helvetica-Bold",
    fontSize=13,
    leading=17,
    textColor=ACCENT,
    spaceBefore=12,
    spaceAfter=5,
)
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14, spaceAfter=5)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=9.5, leading=12.5, spaceAfter=0)
CODE = ParagraphStyle(
    "code",
    fontName="Courier",
    fontSize=9,
    leading=12,
    backColor=colors.HexColor("#f4f4f4"),
    borderPadding=6,
    spaceAfter=8,
)


class Box(Flowable):
    """Empty tick box for checklist items."""

    def wrap(self, *args):
        return (4 * mm, 4 * mm)

    def draw(self):
        self.canv.setStrokeColor(ACCENT)
        self.canv.setLineWidth(0.9)
        self.canv.rect(0, -1, 3.4 * mm, 3.4 * mm)


def inline(text: str) -> str:
    """Markdown inline markup -> reportlab mini-HTML."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("→", "-&gt;")
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links: keep the label
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)


def list_row(marker, text: str, indent: float = 0) -> Table:
    m = marker if isinstance(marker, Flowable) else Paragraph(marker, BODY)
    t = Table([[m, Paragraph(inline(text), BODY)]], colWidths=[7 * mm, None], hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    if not indent:
        return t
    outer = Table([["", t]], colWidths=[indent, None], hAlign="LEFT")
    outer.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return outer


def md_table(rows: list[str]) -> Table:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [cells[0]] + [r for r in cells[2:]]  # drop the |---| separator row
    data = [[Paragraph(f"<b>{inline(c)}</b>", CELL) for c in cells[0]]]
    data += [[Paragraph(inline(c), CELL) for c in r] for r in cells[1:]]
    t = Table(data, repeatRows=1, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, GRID),
                ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def parse(md: str, skip: set[str]) -> list:
    story, section = [], []
    lines = md.splitlines()
    i, skipping = 0, False

    def flush():
        if section:
            story.append(KeepTogether(section[:]) if len(section) < 25 else section[0])
            if len(section) >= 25:
                story.extend(section[1:])
            section.clear()

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("## "):
            flush()
            skipping = s[3:].strip() in skip
            if not skipping:
                section.append(Paragraph(inline(s[3:]), H2))
            i += 1
            continue
        if skipping:
            i += 1
            continue
        if s.startswith("# "):
            story.append(Paragraph(inline(s[2:]), TITLE))
        elif s.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            section.append(Preformatted("\n".join(block), CODE))
        elif s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            section.append(md_table(rows))
            section.append(Spacer(1, 6))
            continue
        elif s:
            indented = line.startswith("   ") or line.startswith("  ")
            text, marker = s, None
            if s.startswith("- [ ] "):
                text, marker = s[6:], Box()
            elif s.startswith("- "):
                text, marker = s[2:], "&ndash;" if indented else "&bull;"
            elif re.match(r"\d+\. ", s):
                num, text = s.split(" ", 1)
                marker = num
            # continuation lines belong to the item / paragraph above
            while i + 1 < len(lines):
                nxt = lines[i + 1]
                ns = nxt.strip()
                if not ns or ns.startswith(("- ", "|", "```", "#")) or re.match(r"\d+\. ", ns):
                    break
                text += " " + ns
                i += 1
            if marker is None:
                section.append(Paragraph(inline(text), BODY))
            else:
                section.append(list_row(marker, text, indent=7 * mm if indented else 0))
        i += 1
    flush()
    return story


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("markdown", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--skip", action="append", default=[], help="section heading to omit")
    args = ap.parse_args()

    out = args.out or args.markdown.with_suffix(".pdf")
    md = args.markdown.read_text()
    title = next((ln[2:] for ln in md.splitlines() if ln.startswith("# ")), out.stem)
    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=title,
    )
    doc.build(parse(md, set(args.skip)))
    print(out)


if __name__ == "__main__":
    main()
