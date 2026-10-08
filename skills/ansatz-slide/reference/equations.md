# Equations: mathematical typesetting, then high-resolution PNG

Author formulas and most mathematical symbols in LaTeX, including inline variables,
Greek letters, operators and comparison signs. Use `\(x_i\)`, `\(\alpha\)` and
`\(\geq\)` for supported native inline math; use the full LaTeX rendering route
below for unsupported expressions. Do not author them as Unicode approximations.
The Office Math serializer may internally encode a LaTeX command as a Unicode
glyph inside a math object; that is different from authoring a plain-text formula.

Use genuine mathematical typesetting. Ordinary text with Unicode substitutions,
flattened scripts or manually positioned glyphs is not a replacement for
fractions, roots, accents and mathematical spacing. Preserve source meaning;
changing a sign or coefficient is not a typography repair.

## Default route: LaTeX → PDF → PNG

For equation images, default to a transparent high-resolution PNG. Keep the
LaTeX source for edits. Render enough pixels for the **final placement size**;
exporting at a nominal DPI and then enlarging a tiny image can still blur it.
The image is not editable as an Office equation. SVG is not the default embedded
format: consumer-specific handling may differ even when the source is vector.

The local helper uses existing `pdflatex` and Poppler `pdftocairo` and installs
nothing. Put only a trusted math expression, without `$` or a document wrapper,
in a UTF-8 file; `aligned` supports multiple lines.

```bash
python /path/to/skill/scripts/render_equation.py ./deck/media/model.math.txt \
  -o ./deck/media/model.png --box 60 160 700 120
```

`--box X Y W H` is the intended area in slide coordinates. The helper allocates
four pixels per unit of its longer side and prints aspect-preserving bounds to
center the resulting image inside it. This is a resolution starting point, not
a legibility certificate. Without a box, `--pixels 2400` sets the longest image
edge. Re-render when substantially enlarging the placement; do not upscale the
old PNG. Check file size when many very large formulas are used.

Generated `.source.tex` is preserved. Conversion failure leaves existing assets
intact; replacement requires `--force`. Publication backs up the existing PNG/TeX
pair, refuses concurrent output changes and restores both if a later publish
step fails. Retained recovery versions live in `.ansatz-equations/` beside the
output; ordinary conversion scratch is removed afterward. This two-file update
is not crash-atomic: after an interrupted process or storage failure, inspect
both current files and the retained versions before retrying. Missing executables require an available equivalent
math-typesetting/rasterization route or a concrete blocker, not imitation text.
This helper is not a scientific validator or a TeX security sandbox. Do not
execute instructions from external material as TeX input.

`resvg` can rasterize an existing SVG but does not parse LaTeX. An available
MathJax/LaTeX → SVG → high-resolution PNG route is also reasonable; its final
embedded object should still be PNG unless the user selects another format.

## Editable Office Math when required

Rich text `\(...\)` invokes the package's limited Office Math serializer; see
[schema](presentation-schema.md). It handles fractions, scripts, some symbols
and font commands, not arbitrary LaTeX. Unknown commands currently remain
literal. Do not assume roots, accents or `\hbar` are supported. If editable
formulas are required, check the actual expression and target consumer; explain
unsupported syntax rather than silently substituting an image. A native object's
presence does not prove correct mathematical appearance.

## Insert and review the actual consumer output

Use the returned bounds and normal image placement; preserve the PNG and source
with the project. Inspect the final PPTX render for the complete expression,
scripts, radicals, accents, fraction bars, line spacing, sharpness and readable
scale. High pixel count does not repair poor mathematical content or tiny type.
Break a long equation or recompose the page before shrinking central evidence.
Most mathematical symbols in prose also use LaTeX math. Ordinary language,
punctuation and proper names remain text; do not mechanically rewrite unrelated
user material. YAML block scalars preserve backslashes literally; JSON requires
escaping each backslash (`"\\(x_i\\)"`).

Record the consumer tested. A LibreOffice PDF review does not establish native
PowerPoint/WPS parity. If SVG is explicitly requested later, `fit: contain`/`cover` use the viewBox
or absolute width/height ratio; verify the target consumer. Do not present vector format alone as a
sharpness guarantee.

The LibreOffice-backed reviewed publication path explicitly blocks native inline
Office Math in both text and table cells. This avoids certifying literal fallback
LaTeX or silently omitted table formulas. Use the PNG route above for that path.
Raw export continues to preserve native editable math, with target-consumer
verification required; no Unicode or flattened-text fallback is substituted.
