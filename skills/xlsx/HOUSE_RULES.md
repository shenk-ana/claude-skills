# House rules (this fork)

These rules come from this fork, not from upstream. Where they differ from `SKILL.md`, **these win**.
They are kept in this separate file so that syncing with `anthropics/skills` does not conflict.

## Font

- **Meiryo UI everywhere**: cell text, every run of rich text, and text inside shapes. Keep each run's
  color, bold, italic and size; change only the font name. This replaces the "Professional font" line in `SKILL.md`.
- Change the **Normal style too** (`styles.xml` font 0; drop its `<scheme val="minor"/>`), and the theme's
  `majorFont` / `minorFont`. Otherwise row/column headers, empty cells and the hidden cells of a merge keep the old font.
- Column widths are measured in the Normal font's max digit width (MDW). After changing the Normal font,
  convert every `<col width>` and `defaultColWidth` so the **pixel** width stays the same
  (MS PGothic 11pt = 7px, Meiryo UI 11pt = 9px).
- Meiryo UI is proportional. To size a column or place a shape against text, measure it:
  `PIL.ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", size_px, index=2).getlength(text)` (index 2 = Meiryo UI).

## Before editing an existing workbook

1. `unzip -l` the file and take stock of **everything that is not a cell**: `xl/drawings/` (red frames,
   callouts, text boxes, arrows), `xl/media/`, `xl/charts/`, comments, `vmlDrawing`.
2. Read the shapes as content: their text (`<a:t>`), where they are anchored, and what they point at.
   Understand them together with the cells before changing anything.
3. Load with `load_workbook(path, rich_text=True)`. Without it, cells pasted from an IDE lose their
   per-token colors and fonts.
4. Edit the original sheet in place. Do not delete and rebuild a sheet that can be kept.
5. Keep the file's own conventions (colors, fills, headings, wording) unless the user asks for a change.

## Shapes after an openpyxl save

openpyxl drops shapes when it saves, so put them back as the last step
(`scripts/add_shapes.py`, see [FLOWCHART.md](FLOWCHART.md), or re-inject the original `drawingN.xml`).

- When rows or columns moved, recompute every anchor; check that each frame still surrounds its target.
- Give shape text an explicit font (`<a:latin>`, `<a:ea>`, `<a:cs>`), also on empty paragraphs (`<a:endParaRPr>`).
- Do not use `vertOverflow="clip"` / `horzOverflow="clip"`; size the shape so all text shows.
- When writing sheet XML by hand, make sure the root declares every prefix it uses (`xmlns:r` for `<drawing r:id>`),
  then parse every part with `xml.etree.ElementTree` (minidom does not catch an unbound prefix; Excel refuses the file).

## Writing documentation workbooks

- A table stays a table; merged cells are fine there. A plain sentence outside a table goes into its own cell:
  no merge, no wrap. Split a long sentence over two rows.
- Size a table to its content. Do not stretch it to the right edge of the sheet.
- Headings are `■Heading`, with no number after `■`.
- Supplementary notes go **last**, under `■補足`, one `※` per note.
- State each fact once. If a behavior applies to several items, put it in one shared place.
- Do not add a row to the revision history unless the user asks.

## Before handing over

- Compare the part list (`unzip -l`) of the original and the new file: nothing may be missing.
- Render and look at it: `soffice --headless --convert-to pdf`, then PyMuPDF (`fitz`) → PNG.
  This renders the file, it is not a screen capture. Check that code stays inside its border, frames sit on their
  lines, callouts show all text, and each sheet prints on the intended number of pages.
- Leave no library name in `docProps/core.xml` / `app.xml` (openpyxl writes `creator = "openpyxl"`):
  keep the original author, or leave it empty.
