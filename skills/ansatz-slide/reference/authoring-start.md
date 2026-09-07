# Small, executable authoring subset

Start with text, image assets, rectangles and lines. Native charts/tables are compatibility features, not the default way to make figures. The following blocks form one complete two-file project; they are regression-tested through the actual writer.

Use `pptx.yaml` for the manifest and `*.page.yaml` for pages.

## `pptx.yaml`

```yaml
version: v2
title: Evidence-led report
size: [960, 540]
pages:
  - pages/01.page.yaml
```

## `pages/01.page.yaml`

```yaml
pageType: content
background: {type: solid, color: "#FFFFFF"}
elements:
  - elementId: title
    elementType: text
    bounds: [48, 36, 864, 64]
    content:
      fontFamily: Arial
      fontSize: 32
      color: "#172C34"
      bold: true
      text: "A clear claim needs visible evidence"
  - elementId: evidence-frame
    elementType: shape
    bounds: [48, 140, 540, 300]
    shapeName: rect
    fill: {type: solid, color: "#F1F4F7"}
  - elementId: missing-evidence
    elementType: text
    bounds: [72, 245, 492, 72]
    content:
      fontFamily: Arial
      fontSize: 22
      color: "#172C34"
      text: "Evidence asset pending — not a measured result"
  - elementId: interpretation
    elementType: text
    bounds: [628, 160, 284, 210]
    content:
      fontFamily: Arial
      fontSize: 22
      color: "#172C34"
      text: "Replace this explanation with what the supplied evidence supports."
```

This is a structural starter, not a completed report or a font-availability guarantee. Choose installed Latin/East Asian fonts for the audience and inspect the final render. Colors and layout may change; field names and types may not be invented.

For a supplied figure, replace both `evidence-frame` and `missing-evidence` with one `image` element: give it a unique `elementId`, `bounds: [48, 140, 540, 300]`, `src: media/figure.png`, and `fit: {mode: contain}`. The file must actually exist inside the project. Keep interpretation and source as separate native text.

Important distinctions:

- `bounds` is `[x, y, width, height]`, not `[left, top, right, bottom]`.
- `.page.yaml` elements are in back-to-front order. A separate shape and text may intentionally overlap; unrelated text must not.
- Native text must not contain element-level opacity, rotation or flip. Use a solid color or disclose an external-image substitute.
- Prefer JSON serialization or quoted YAML/block scalars for text containing `:`, `#` or HTML. Do not paste TypeScript interface notation into a page.
- Validate via the manifest, not a standalone page YAML file. From an installed skill, run `python3 scripts/ansatz_slide.py validate <project>`; use `python3 scripts/ansatz_slide.py export <project> -o output.pptx` to export.
