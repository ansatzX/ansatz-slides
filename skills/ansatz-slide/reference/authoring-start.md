# Small, executable authoring subset

Start with text, image assets, rectangles and lines. Native charts/tables are compatibility features, not the default way to make figures. The following blocks form the two authoring inputs for a new project; they are regression-tested through the actual writer.

Save the first block as `settings.yaml` and the second as `first.page.yaml`.
Run `ansatz-slide deck create ./deck --settings ./settings.yaml --content ./first.page.yaml`.
The CLI manages page filenames and the formal manifest. A blocked result retains
the candidate and matrices for `page update WORK`; a successful result includes
the first preview. Keep local assets inside `./deck` when used.

## `settings.yaml`

```yaml
version: v2
title: Evidence-led report
size: [960, 540]
```

## `first.page.yaml`

```yaml
pageType: content
allowedOverlaps:
  - elements: [evidence-frame, missing-evidence]
    reason: The evidence placeholder label belongs inside its background frame.
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

For a supplied figure, replace both `evidence-frame` and `missing-evidence` with one `image` element: give it a unique `elementId`, `bounds: [48, 140, 540, 300]`, `src: media/figure.png`, and `fit: {mode: contain}`. Remove the obsolete `allowedOverlaps` pair when removing those two elements. The file must actually exist inside the project. Keep interpretation and source as separate native text.

Important distinctions:

- `bounds` is `[x, y, width, height]`, not `[left, top, right, bottom]`.
- `.page.yaml` elements are in back-to-front order. A separate shape and text may intentionally overlap; unrelated text must not.
- Native text must not contain element-level opacity, rotation or flip. Use a solid color or disclose an external-image substitute.
- Prefer JSON serialization or quoted YAML/block scalars for text containing `:`, `#` or HTML. Do not paste TypeScript interface notation into a page.
- Validate via the manifest, not a standalone page YAML file. From an installed skill, run `python3 scripts/ansatz_slide.py validate <project>`; use `python3 scripts/ansatz_slide.py deck export <project> -o output.pptx` to export.
