# Design-system runtime contract

Read this before applying any preset. Presets describe visual intent, not additional pptx.yaml syntax or proof of export support.

## 1. Methodology and evidence

Follow the user's content, audience, and evidence first. A style's density targets never authorize invented measurements, copied source-deck claims, fabricated citations, or filler. Missing evidence may be an explicitly labeled asset placeholder. Synthetic demonstration data must be labeled as such. Source-deck observations in presets are upstream descriptions, not independently verified facts about this exporter.

## 2. Visual system

Select one preset; its PART B overrides its category's PART A for appearance. Preserve its palette, hierarchy, reading order and signature layout while fitting the actual content. A one-page example demonstrates a page type, not the complete deck-wide rhythm.

Interpret all preset density quotas, page-type frequencies, card/color prohibitions and “fill every region” statements as style defaults, subordinate to the user's template, evidence, readability and runtime constraints. They do not authorize invented results, illegible text, forced decorative assets or changes to unrelated pages. Empty space may be intentional; an explicitly pending evidence asset is preferable to fabricated content. References to SmartArt, custom fonts, diagrams or charts describe visual intent, not an implementation entry point.

Resolve a theme ID to `design_system/<category>/<id>/design.md` when present. Numbered directories are alternate descriptions: do not silently combine a same-ID alternate with the primary. Use an alternate only when the user explicitly selects its path. See [the complete inventory](design-system-inventory.md).

## 3. Executable DSL

The [pptx.yaml reference](presentation-schema.md) and strict local validator determine executable syntax. Never translate prose literally into new fields. Do not weaken validation to accommodate a style.

- Image fitting is an object: `fit: {mode: contain}` or `fit: {mode: cover}`, not a scalar. Crop is numeric, e.g. `crop: {top: 0.2, bottom: 0.2}`; opposite sides must sum to less than 1. Use `contain` for complete figures/tables unless cropping is expressly intended.
- Native text must not carry element-level `opacity`, `rotation`, or `flip`. For faint text on a known solid background, calculate a preblended solid color; for a required rotated treatment, obtain an external image and disclose that this element is no longer editable text.
- Palette nicknames are design tokens, not automatically resolved colors. Map them to legal color values or explicitly defined supported theme tokens.
- `customFonts` entries require both `family` and `src`. Merely naming a font in a style does not install it, license it, or embed it in PPTX. Verify target fonts or document a tested replacement. Exact line wrapping across Office consumers is not guaranteed.
- Produce charts, diagrams and finished tables with an external tool, or use user-supplied files. Embed these as image assets; keep titles, explanations and sources as native text. The pptx.yaml layer lays out these assets; it does not need to redraw them as native charts/tables.
- Heatmaps and similar visual recommendations mean external assets, not permission to use unsupported native chart series. Local native `candlestick`, `heatmap`, `treemap`, `sunburst`, and `sankey` remain rejected. Prepare unsupported visualizations externally and use supported image fields.
- For faithful icons use supplied/licensed PNG/SVG assets. `iconName: fas:...` is compatibility syntax, not a promise of a faithful vector icon in PowerPoint; the local writer has a generic fallback.

## 4. Delivery and verification

Keep the manifest, individual `.page.yaml` files and referenced media. Export through the strict local CLI, inspect the PPTX ZIP/OOXML and render the exported PPTX—not only the editor preview. Check fit, crops, labels, wrapping, fonts and native text separately. A successful export does not establish visual fidelity.

For edits to one page, follow SKILL.md's incremental replacement workflow and test unchanged-page OOXML semantics. Applying a style must not silently rewrite other pages or shared assets.

Theme thumbnails are style-reference images, not proven outputs of the current skill. Only examples accompanied by executable source, assets, output and verification may be presented as generated demonstrations.
