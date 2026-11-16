#!/usr/bin/env python3
"""Draw native, editable Excel shapes (flowcharts, box diagrams) into an .xlsx.

Writes DrawingML straight into the package, so it needs no Excel and no
renderer. Run it as the LAST step: openpyxl drops shapes on save.

    python scripts/add_shapes.py book.xlsx spec.json            # edits in place
    python scripts/add_shapes.py book.xlsx spec.json -o out.xlsx
    python scripts/add_shapes.py book.xlsx spec.json --plan     # report only

Spec (all sizes in pixels at 96 dpi, relative to the anchor cell's top-left):

    {
      "sheet": "Flow",                 # default: first sheet
      "anchor": "B3",                  # default: A1
      "font": "Meiryo UI", "font_size": 10,
      "shapes": [
        {"id": "s", "type": "flowChartTerminator", "text": "開始",
         "x": 40, "y": 0, "w": 140, "h": 40},
        {"id": "q", "type": "flowChartDecision", "text": "OK?",
         "x": 40, "y": 80, "w": 140, "h": 70, "fill": "FFF2CC"}
      ],
      "connectors": [
        {"from": "s", "to": "q"},
        {"from": "q", "to": "s", "from_side": "r", "to_side": "r",
         "via": [[220, 115], [220, 20]], "label": "No"}
      ]
    }

Shape keys: type (any DrawingML preset: rect, roundRect, flowChartProcess,
flowChartDecision, flowChartTerminator, flowChartDocument, ...; default
flowChartProcess), text ("\\n" for line breaks), fill / line (RRGGBB or
"none"), font_color, font_size, bold.
Connector keys: from, to, from_side / to_side (t, b, l, r; chosen from the
shapes' relative position when omitted), via (bend points; each leg is a
straight segment), label, color, dash (true for a dashed line).

Prints JSON: the rows the drawing covers and `next_free_row`. Rows it covers
get an explicit height, so the layout no longer depends on the viewer's
default row height. Exits 1 without writing if a non-empty cell lies under
the drawing.
"""

import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from lxml import etree

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
REL_DRAWING = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"
CT_DRAWING = "application/vnd.openxmlformats-officedocument.drawing+xml"
EMU_PER_PX = 9525
PT_PER_PX = 0.75
# Connection-site index of each side. Every rectangular and flowChart preset
# lists its sites top, left, bottom, right.
SITE = {"t": 0, "l": 1, "b": 2, "r": 3}
# Elements that must come after <drawing> in a worksheet (CT_Worksheet order).
AFTER_DRAWING = ["legacyDrawing", "legacyDrawingHF", "drawingHF", "picture",
                 "oleObjects", "controls", "webPublishItems", "tableParts", "extLst"]


def q(prefix, tag):
    return f"{{{NS[prefix]}}}{tag}"


def col_to_idx(letters):
    n = 0
    for ch in letters.upper():
        n = n * 26 + ord(ch) - 64
    return n


def split_ref(ref):
    m = re.fullmatch(r"([A-Za-z]+)(\d+)", ref)
    if not m:
        raise SystemExit(f"bad cell reference: {ref}")
    return col_to_idx(m.group(1)), int(m.group(2))


def col_px(width_chars):
    # Excel's conversion for a 7-px max digit width (the Calibri 11 default).
    return int((256 * width_chars + int(128 / 7)) / 256 * 7)


class Sheet:
    def __init__(self, root):
        self.root = root
        fmt = root.find(q("m", "sheetFormatPr"))
        self.default_ht = float(fmt.get("defaultRowHeight", 15)) if fmt is not None else 15.0
        default_w = fmt.get("defaultColWidth") if fmt is not None else None
        self.default_col_px = col_px(float(default_w)) if default_w else 64
        self.col_widths = {}
        cols = root.find(q("m", "cols"))
        for c in cols if cols is not None else []:
            for i in range(int(c.get("min")), int(c.get("max")) + 1):
                if c.get("hidden") == "1":
                    self.col_widths[i] = 0
                elif c.get("width"):
                    self.col_widths[i] = col_px(float(c.get("width")))
        self.sheet_data = root.find(q("m", "sheetData"))
        self.rows = {int(r.get("r")): r for r in self.sheet_data.findall(q("m", "row"))}

    def row_pt(self, r):
        row = self.rows.get(r)
        if row is not None and row.get("ht"):
            return float(row.get("ht"))
        return self.default_ht

    def col_width_px(self, c):
        return self.col_widths.get(c, self.default_col_px)

    def span(self, start, extent, size_of):
        """Last index covered when `extent` units are laid from the start of `start`."""
        i, used = start, size_of(start)
        while used < extent:
            i += 1
            used += size_of(i)
        return i

    def fix_row_heights(self, first, last):
        for r in range(first, last + 1):
            row = self.rows.get(r)
            if row is None:
                row = etree.Element(q("m", "row"), r=str(r))
                later = [n for n in self.rows if n > r]
                if later:
                    self.rows[min(later)].addprevious(row)
                else:
                    self.sheet_data.append(row)
                self.rows[r] = row
            if not row.get("ht"):
                row.set("ht", str(self.default_ht))
            row.set("customHeight", "1")

    def filled_cells(self, c0, c1, r0, r1):
        hits = []
        for r in range(r0, r1 + 1):
            row = self.rows.get(r)
            if row is None:
                continue
            for c in row.findall(q("m", "c")):
                col, _ = split_ref(c.get("r"))
                has_value = c.find(q("m", "v")) is not None or c.find(q("m", "is")) is not None
                if c0 <= col <= c1 and has_value:
                    hits.append(c.get("r"))
        return hits

    def add_drawing_ref(self, rid):
        el = etree.Element(q("m", "drawing"))
        el.set(q("r", "id"), rid)
        for name in AFTER_DRAWING:
            nxt = self.root.find(q("m", name))
            if nxt is not None:
                nxt.addprevious(el)
                return
        self.root.append(el)


def resolve(base_dir, target):
    if target.startswith("/"):
        return target.lstrip("/")
    return str(PurePosixPath(base_dir, target)).replace("\\", "/")


def normalize(path):
    parts = []
    for p in path.split("/"):
        if p == "..":
            parts.pop()
        elif p and p != ".":
            parts.append(p)
    return "/".join(parts)


def sheet_path(files, name):
    wb = etree.fromstring(files["xl/workbook.xml"])
    rels = etree.fromstring(files["xl/_rels/workbook.xml.rels"])
    sheets = wb.find(q("m", "sheets"))
    chosen = sheets[0] if name is None else next(
        (s for s in sheets if s.get("name") == name), None)
    if chosen is None:
        raise SystemExit(f"no sheet named {name!r}")
    rid = chosen.get(q("r", "id"))
    target = next(r.get("Target") for r in rels if r.get("Id") == rid)
    return normalize(resolve("xl", target))


def rels_path(part):
    p = PurePosixPath(part)
    return str(p.parent / "_rels" / (p.name + ".rels"))


def new_rels():
    return etree.Element(q("pr", "Relationships"), nsmap={None: NS["pr"]})


def solid(parent, color):
    if color == "none":
        etree.SubElement(parent, q("a", "noFill"))
    else:
        fill = etree.SubElement(parent, q("a", "solidFill"))
        etree.SubElement(fill, q("a", "srgbClr"), val=color)


def group_anchor(row0, col0, gid, w, h):
    """One oneCellAnchor at the anchor cell holding a group of every shape.

    Excel clamps an anchor's colOff/rowOff to the size of its cell, so each
    shape cannot carry its own far-away offset. Inside a group, children use
    plain EMU coordinates and never depend on column widths or row heights.
    """
    anc = etree.Element(q("xdr", "oneCellAnchor"))
    frm = etree.SubElement(anc, q("xdr", "from"))
    for tag, val in (("col", col0 - 1), ("colOff", 0), ("row", row0 - 1), ("rowOff", 0)):
        etree.SubElement(frm, q("xdr", tag)).text = str(val)
    cx, cy = str(round(w * EMU_PER_PX)), str(round(h * EMU_PER_PX))
    etree.SubElement(anc, q("xdr", "ext"), cx=cx, cy=cy)
    grp = etree.SubElement(anc, q("xdr", "grpSp"))
    nv = etree.SubElement(grp, q("xdr", "nvGrpSpPr"))
    etree.SubElement(nv, q("xdr", "cNvPr"), id=str(gid), name=f"Diagram {gid}")
    etree.SubElement(nv, q("xdr", "cNvGrpSpPr"))
    gpr = etree.SubElement(grp, q("xdr", "grpSpPr"))
    xf = etree.SubElement(gpr, q("a", "xfrm"))
    etree.SubElement(xf, q("a", "off"), x="0", y="0")
    etree.SubElement(xf, q("a", "ext"), cx=cx, cy=cy)
    etree.SubElement(xf, q("a", "chOff"), x="0", y="0")
    etree.SubElement(xf, q("a", "chExt"), cx=cx, cy=cy)
    etree.SubElement(anc, q("xdr", "clientData"))
    return anc, grp


def xfrm(parent, x, y, w, h, flip_h=False, flip_v=False):
    attrs = {}
    if flip_h:
        attrs["flipH"] = "1"
    if flip_v:
        attrs["flipV"] = "1"
    xf = etree.SubElement(parent, q("a", "xfrm"), **attrs)
    etree.SubElement(xf, q("a", "off"), x=str(round(x * EMU_PER_PX)), y=str(round(y * EMU_PER_PX)))
    etree.SubElement(xf, q("a", "ext"), cx=str(round(w * EMU_PER_PX)), cy=str(round(h * EMU_PER_PX)))


def text_body(parent, text, font, size, color, bold):
    body = etree.SubElement(parent, q("xdr", "txBody"))
    etree.SubElement(body, q("a", "bodyPr"), vertOverflow="clip", horzOverflow="clip",
                     wrap="square", lIns="36000", tIns="0", rIns="36000", bIns="0",
                     rtlCol="0", anchor="ctr")
    etree.SubElement(body, q("a", "lstStyle"))
    for line in str(text).split("\n"):
        p = etree.SubElement(body, q("a", "p"))
        etree.SubElement(p, q("a", "pPr"), algn="ctr")
        run = etree.SubElement(p, q("a", "r"))
        rpr = etree.SubElement(run, q("a", "rPr"), lang="ja-JP", altLang="en-US",
                               sz=str(int(size * 100)), b="1" if bold else "0")
        solid(rpr, color)
        for tag in ("latin", "ea", "cs"):
            etree.SubElement(rpr, q("a", tag), typeface=font)
        etree.SubElement(run, q("a", "t")).text = line


def shape_el(sid, name, s, font, size):
    sp = etree.Element(q("xdr", "sp"), macro="", textlink="")
    nv = etree.SubElement(sp, q("xdr", "nvSpPr"))
    etree.SubElement(nv, q("xdr", "cNvPr"), id=str(sid), name=name)
    etree.SubElement(nv, q("xdr", "cNvSpPr"))
    pr = etree.SubElement(sp, q("xdr", "spPr"))
    xfrm(pr, s["x"], s["y"], s["w"], s["h"])
    geom = etree.SubElement(pr, q("a", "prstGeom"), prst=s.get("type", "flowChartProcess"))
    etree.SubElement(geom, q("a", "avLst"))
    solid(pr, s.get("fill", "FFFFFF"))
    ln = etree.SubElement(pr, q("a", "ln"), w="12700")
    solid(ln, s.get("line", "000000"))
    text_body(sp, s.get("text", ""), font, s.get("font_size", size),
              s.get("font_color", "000000"), s.get("bold", False))
    return sp


def connector_el(sid, name, p1, p2, start, end, arrow, color, dash):
    x, y = min(p1[0], p2[0]), min(p1[1], p2[1])
    w, h = abs(p2[0] - p1[0]), abs(p2[1] - p1[1])
    cx = etree.Element(q("xdr", "cxnSp"), macro="")
    nv = etree.SubElement(cx, q("xdr", "nvCxnSpPr"))
    etree.SubElement(nv, q("xdr", "cNvPr"), id=str(sid), name=name)
    cnv = etree.SubElement(nv, q("xdr", "cNvCxnSpPr"))
    if start:
        etree.SubElement(cnv, q("a", "stCxn"), id=str(start[0]), idx=str(start[1]))
    if end:
        etree.SubElement(cnv, q("a", "endCxn"), id=str(end[0]), idx=str(end[1]))
    pr = etree.SubElement(cx, q("xdr", "spPr"))
    xfrm(pr, x, y, w, h, flip_h=p2[0] < p1[0], flip_v=p2[1] < p1[1])
    geom = etree.SubElement(pr, q("a", "prstGeom"), prst="straightConnector1")
    etree.SubElement(geom, q("a", "avLst"))
    ln = etree.SubElement(pr, q("a", "ln"), w="12700")
    solid(ln, color)
    if dash:
        etree.SubElement(ln, q("a", "prstDash"), val="dash")
    if arrow:
        etree.SubElement(ln, q("a", "tailEnd"), type="triangle")
    return cx


def renumber(wsdr):
    """Give objects ids 2, 3, ... in document order and remap connector ends.

    Excel renumbers this way on load (an openpyxl image is written with id 1)
    but does not remap stCxn/endCxn, so connectors would attach to the wrong
    shape unless the file already holds the ids Excel will assign.
    """
    mapping = {}
    for n, el in enumerate(wsdr.iter(q("xdr", "cNvPr")), start=2):
        mapping[el.get("id")] = str(n)
        el.set("id", str(n))
    for tag in ("stCxn", "endCxn"):
        for el in wsdr.iter(q("a", tag)):
            el.set("id", mapping.get(el.get("id"), el.get("id")))


def side_point(s, side):
    x, y, w, h = s["x"], s["y"], s["w"], s["h"]
    return {"t": (x + w / 2, y), "b": (x + w / 2, y + h),
            "l": (x, y + h / 2), "r": (x + w, y + h / 2)}[side]


def auto_sides(a, b):
    dx = (b["x"] + b["w"] / 2) - (a["x"] + a["w"] / 2)
    dy = (b["y"] + b["h"] / 2) - (a["y"] + a["h"] / 2)
    if abs(dy) >= abs(dx):
        return ("b", "t") if dy >= 0 else ("t", "b")
    return ("r", "l") if dx >= 0 else ("l", "r")


def build(files, spec):
    shapes = spec.get("shapes", [])
    by_id = {s["id"]: s for s in shapes}
    if len(by_id) != len(shapes):
        raise SystemExit("shape ids must be unique")
    for c in spec.get("connectors", []):
        for key in ("from", "to"):
            if c[key] not in by_id:
                raise SystemExit(f"connector {key} {c[key]!r} is not a shape id")

    path = sheet_path(files, spec.get("sheet"))
    root = etree.fromstring(files[path])
    sheet = Sheet(root)
    col0, row0 = split_ref(spec.get("anchor", "A1"))

    points = [(s["x"], s["y"]) for s in shapes] + [(s["x"] + s["w"], s["y"] + s["h"]) for s in shapes]
    for c in spec.get("connectors", []):
        points += [tuple(p) for p in c.get("via", [])]
    if min(min(p) for p in points) < 0:
        raise SystemExit("x and y must be >= 0 (they are offsets from the anchor cell)")
    right_px = max(p[0] for p in points) + 60  # room for connector labels
    bottom_pt = max(p[1] for p in points) * PT_PER_PX
    last_col = sheet.span(col0, right_px, sheet.col_width_px)
    last_row = sheet.span(row0, bottom_pt, sheet.row_pt)
    extent = (right_px, max(p[1] for p in points))
    return path, root, sheet, col0, row0, last_col, last_row, by_id, extent


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("xlsx")
    ap.add_argument("spec")
    ap.add_argument("-o", "--output")
    ap.add_argument("--plan", action="store_true", help="report the covered range, write nothing")
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    with zipfile.ZipFile(args.xlsx) as z:
        names = z.namelist()
        files = {n: z.read(n) for n in names}

    path, root, sheet, col0, row0, last_col, last_row, by_id, extent = build(files, spec)
    report = {"sheet_part": path, "rows": [row0, last_row], "cols": [col0, last_col],
              "next_free_row": last_row + 2}
    filled = sheet.filled_cells(col0, last_col, row0, last_row)
    if filled:
        report["error"] = "cells under the drawing are not empty"
        report["cells"] = filled[:50]
        print(json.dumps(report, ensure_ascii=False, indent=2))
        sys.exit(1)
    if args.plan:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    sheet.fix_row_heights(row0, last_row)

    # Reuse the sheet's drawing part if it has one (images, charts), else add one.
    srels_name = rels_path(path)
    srels = etree.fromstring(files[srels_name]) if srels_name in files else new_rels()
    dref = root.find(q("m", "drawing"))
    if dref is not None:
        rid = dref.get(q("r", "id"))
        target = next(r.get("Target") for r in srels if r.get("Id") == rid)
        dpath = normalize(resolve(str(PurePosixPath(path).parent), target))
        wsdr = etree.fromstring(files[dpath])
    else:
        n = 1
        while f"xl/drawings/drawing{n}.xml" in files:
            n += 1
        dpath = f"xl/drawings/drawing{n}.xml"
        used = {r.get("Id") for r in srels}
        k = 1
        while f"rId{k}" in used:
            k += 1
        rid = f"rId{k}"
        etree.SubElement(srels, q("pr", "Relationship"), Id=rid, Type=REL_DRAWING,
                         Target=f"../drawings/drawing{n}.xml")
        sheet.add_drawing_ref(rid)
        wsdr = etree.Element(q("xdr", "wsDr"), nsmap={"xdr": NS["xdr"], "a": NS["a"]})
        ct = etree.fromstring(files["[Content_Types].xml"])
        etree.SubElement(ct, q("ct", "Override"), PartName="/" + dpath, ContentType=CT_DRAWING)
        files["[Content_Types].xml"] = etree.tostring(ct, xml_declaration=True, encoding="UTF-8", standalone=True)
        files[srels_name] = etree.tostring(srels, xml_declaration=True, encoding="UTF-8", standalone=True)

    next_id = 1 + max([int(e.get("id")) for e in wsdr.iter(q("xdr", "cNvPr"))] or [1])
    font, size = spec.get("font", "Meiryo UI"), spec.get("font_size", 10)
    anc, grp = group_anchor(row0, col0, next_id, extent[0], extent[1])
    wsdr.append(anc)
    next_id += 1
    ids = {}
    for s in by_id.values():
        ids[s["id"]] = next_id
        grp.append(shape_el(next_id, s["id"], s, font, size))
        next_id += 1

    for c in spec.get("connectors", []):
        a, b = by_id[c["from"]], by_id[c["to"]]
        fs, ts = auto_sides(a, b)
        fs, ts = c.get("from_side", fs), c.get("to_side", ts)
        pts = [side_point(a, fs)] + [tuple(p) for p in c.get("via", [])] + [side_point(b, ts)]
        legs = list(zip(pts, pts[1:]))
        for i, (p1, p2) in enumerate(legs):
            start = (ids[c["from"]], SITE[fs]) if i == 0 else None
            end = (ids[c["to"]], SITE[ts]) if i == len(legs) - 1 else None
            grp.append(connector_el(next_id, f"{c['from']}->{c['to']} #{i + 1}", p1, p2, start, end,
                                    i == len(legs) - 1, c.get("color", "000000"),
                                    c.get("dash", False)))
            next_id += 1
        if c.get("label"):
            # Put the label beside the middle of the first leg.
            (x1, y1), (x2, y2) = legs[0]
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            label = {"x": mx + 4, "y": my - 10, "w": 48, "h": 20, "type": "rect",
                     "fill": "none", "line": "none", "text": c["label"]}
            grp.append(shape_el(next_id, f"label {c['from']}->{c['to']}", label, font, size))
            next_id += 1

    renumber(wsdr)
    files[dpath] = etree.tostring(wsdr, xml_declaration=True, encoding="UTF-8", standalone=True)
    files[path] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    out = args.output or args.xlsx
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx",
                                     dir=str(Path(out).resolve().parent)) as tmp:
        tmp_name = tmp.name
    with zipfile.ZipFile(tmp_name, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names + [n for n in files if n not in names]:
            z.writestr(n, files[n])
    shutil.move(tmp_name, out)
    report["output"] = out
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
