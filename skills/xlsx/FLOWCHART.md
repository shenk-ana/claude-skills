# Flowcharts and diagrams in Excel

Draw diagrams as **native Excel shapes** by default: the user can move a box, retype a
label, or reroute an arrow in Excel. Insert a picture only when the user asks for one
or the diagram is too large to lay out by hand.

| Situation | Method |
|---|---|
| Default, any OS, no Excel needed | `scripts/add_shapes.py`: writes DrawingML into the file |
| Windows with Excel installed, and you need Excel's elbow routing or must edit a workbook openpyxl would damage | COM (`win32com`) |
| User wants a picture, or 30+ nodes that need automatic layout | Graphviz/Mermaid → PNG → `openpyxl` |

## Native shapes: `scripts/add_shapes.py`

openpyxl **deletes shapes when it saves**, so this is the last step:
build with openpyxl → `recalc.py` (it keeps shapes) → `add_shapes.py`.

```bash
python scripts/add_shapes.py book.xlsx flow.json --plan   # which rows/cols it covers
python scripts/add_shapes.py book.xlsx flow.json          # edits in place (-o for a copy)
```

```json
{
  "sheet": "処理フロー", "anchor": "B3", "font": "Meiryo UI", "font_size": 10,
  "shapes": [
    {"id": "start", "type": "flowChartTerminator", "text": "開始",      "x": 40,  "y": 0,   "w": 140, "h": 40},
    {"id": "load",  "type": "flowChartProcess",    "text": "CSV読込",   "x": 40,  "y": 70,  "w": 140, "h": 50},
    {"id": "check", "type": "flowChartDecision",   "text": "件数>0?",   "x": 40,  "y": 150, "w": 140, "h": 70, "fill": "FFF2CC"},
    {"id": "end",   "type": "flowChartTerminator", "text": "終了",      "x": 40,  "y": 260, "w": 140, "h": 40},
    {"id": "err",   "type": "flowChartProcess",    "text": "エラー通知", "x": 260, "y": 160, "w": 120, "h": 50}
  ],
  "connectors": [
    {"from": "start", "to": "load"},
    {"from": "load",  "to": "check"},
    {"from": "check", "to": "end", "label": "Yes"},
    {"from": "check", "to": "err", "label": "No"},
    {"from": "err", "to": "load", "from_side": "t", "to_side": "r", "via": [[320, 95]], "dash": true}
  ]
}
```

- **Units are pixels from the anchor cell's top-left corner.** The whole diagram is
  one group anchored to that cell. Positions inside it do not depend on column widths.
- `type` is any DrawingML preset name, such as `rect`, `roundRect`, `flowChartProcess`,
  `flowChartDecision`, `flowChartTerminator`, `flowChartDocument`,
  `flowChartInputOutput`, `flowChartPredefinedProcess`, `flowChartMagneticDisk`.
- A connector picks its sides from the shapes' relative position. To go around
  something, set `from_side`/`to_side` (`t` `b` `l` `r`) and give the bend points in
  `via`. Each leg is a straight line, and only the last leg has the arrowhead.
- Use `\n` in `text` for a line break. Other keys: `fill` and `line` (`RRGGBB` or
  `none`), `font_color`, `font_size`, `bold`.
- **The rows under the diagram get an explicit height.** With that, `next_free_row` in the
  output is exact on every viewer; never estimate it from a default row height. The script
  **refuses to write if a non-empty cell lies under the diagram**, so leave the rows
  clear, or run `--plan` first and put the content below `next_free_row`. Column
  coverage is estimated from a 7-px digit width, so leave a column of slack to the right.
- If the sheet already has a drawing (images, charts), the shapes are added to it.

### Layout that reads well

- Keep one column of boxes on one `x`. Step `y` by box height + 30 px.
- Put side branches to the right, at least 80 px clear of the main column.
- A CJK character at 10 pt is about 14 px wide. Make each box wider than its longest
  line + 20 px, or break the label with `\n`.
- Arrows that loop back go along the outside, using `via` points that clear every box.

## COM (Windows + Excel)

Excel computes the positions and routes elbow connectors itself, so this is the most
faithful method. It only runs where Excel is installed.

```python
import os, pythoncom, win32com.client as win32

PROCESS, DECISION, TERMINATOR = 61, 63, 69      # msoShapeFlowchart*
ELBOW, TRIANGLE = 2, 2                           # msoConnectorElbow, msoArrowheadTriangle

xl = win32.DispatchEx("Excel.Application")      # own hidden instance, never the user's
xl.Visible = False
xl.DisplayAlerts = False
try:
    wb = xl.Workbooks.Open(os.path.abspath("book.xlsx"))
    ws = wb.Worksheets("処理フロー")
    left, top = ws.Range("B3").Left, ws.Range("B3").Top   # points, from Excel itself

    def box(kind, text, x, y, w=105, h=36):
        s = ws.Shapes.AddShape(kind, left + x, top + y, w, h)
        s.Fill.ForeColor.RGB = 0xFFFFFF
        s.Line.ForeColor.RGB = 0
        r = s.TextFrame2.TextRange
        r.Text = text
        r.Font.NameFarEast = r.Font.Name = "Meiryo UI"
        r.Font.Size = 10
        r.Font.Fill.ForeColor.RGB = 0
        r.ParagraphFormat.Alignment = 2          # msoAlignCenter
        s.TextFrame2.VerticalAnchor = 3          # msoAnchorMiddle
        return s

    def arrow(a, b, a_site=3, b_site=1):         # sites: 1 top, 2 left, 3 bottom, 4 right
        c = ws.Shapes.AddConnector(ELBOW, 0, 0, 10, 10)
        c.ConnectorFormat.BeginConnect(a, a_site)
        c.ConnectorFormat.EndConnect(b, b_site)
        c.Line.EndArrowheadStyle = TRIANGLE
        c.Line.ForeColor.RGB = 0
        return c

    s = box(TERMINATOR, "開始", 0, 0)
    p = box(PROCESS, "データ読込", 0, 60)
    q = box(DECISION, "件数>0?", 0, 120, h=50)
    arrow(s, p); arrow(p, q)
    arrow(q, p, 4, 4)                            # loop back on the right side
    wb.Save()
    wb.Close(False)
finally:
    xl.Quit()
    del xl
    pythoncom.CoUninitialize()
```

- COM sizes are **points** (1 px = 0.75 pt), and colors are **BGR** integers.
- Always use `DispatchEx` with `Visible = False`. `Dispatch` can attach to the user's
  open Excel and change their workbooks.
- If the file is open in the user's Excel, `Open`/`Save` fails or opens it read-only.
  Ask the user to close it.
- **A hidden Excel can leave an orphaned `splwow64.exe` behind.** After that, every
  printer shows "接続できません" in the user's Excel. Before starting, note the existing
  `splwow64.exe` PIDs. After `Quit`, end any new one whose parent process is gone.
  Never touch the printer or Spooler settings.

## Picture fallback (Graphviz / Mermaid → PNG)

Check what is installed first: `which dot` and `which mmdc`.

- Prefer Graphviz: it is small and needs no browser. Mermaid CLI pulls in
  Node, Puppeteer and Chromium (100–300 MB), and often fails behind a corporate proxy.
- If neither is installed, **ask before installing**. Suggest Graphviz. If the install is
  denied or fails, use native shapes instead.

```bash
dot -Tpng -Gdpi=200 flow.dot -o flow.png
mmdc -i flow.mmd -o flow.png -b white --scale 3
```

```python
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage

w, h = PILImage.open("flow.png").size
scale = 420 / w                               # target width in px; keep the aspect ratio
img = XLImage("flow.png")
img.width, img.height = round(w * scale), round(h * scale)
ws.add_image(img, "B3")

# Reserve the rows the picture covers, with explicit heights (see above for why).
row_pt = 15
rows = int(img.height * 0.75 / row_pt) + 1
for r in range(3, 3 + rows):
    ws.row_dimensions[r].height = row_pt
next_free_row = 3 + rows + 2
```

- **CJK labels:** neither renderer's default font covers CJK reliably. In DOT, set
  `fontname="Meiryo UI"` (or `"Noto Sans CJK JP"`) on `graph`, `node` and `edge`. For
  Mermaid, set the font with `--cssFile`.
- A render that exits 0 can still have silently dropped a malformed edge. Compare the
  picture with the `.dot`/`.mmd` source.
- The picture cannot be edited in Excel. If the user will maintain the diagram, use
  native shapes.

## Before shipping

- Open the file in Excel, or ask the user to, and look at the diagram. A diagram can be
  valid XML and still overlap or read in the wrong order.
- Re-run `recalc.py` after any later openpyxl save, then re-run `add_shapes.py`:
  that openpyxl save deleted the shapes.
