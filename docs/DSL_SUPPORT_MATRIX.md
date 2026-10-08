# Executable pptx.yaml support matrix

This matrix records what the current `ansatz-slide` package actually validates and exports. Executable boundaries are enforced by the validator, occupancy gate and publication code. Use [the field reference](../skills/ansatz-slide/reference/presentation-schema.md) for syntax and [work objects](../skills/ansatz-slide/reference/review-cli.md) for the current authoring interface.

These statuses describe compatibility, not the preferred authoring workflow. In normal production, figures, charts, and finished tables come from a dedicated tool or the user as PNG/SVG assets; pptx.yaml/PPTX performs layout, captions, annotations, and sourcing. Native chart/table DSL remains tested so existing legal inputs cannot silently degrade.

## Status meanings

- **Verified**: exercised through the local writer and inspected in OOXML and/or rendered output.
- **Supported with boundary**: usable under the stated constraint; no broader guarantee is made.
- **Rejected**: the strict validator stops before any PPTX is written because the local writer was proven to drop or misrepresent the construct.
- **Not provided**: no implementation entry point exists and the skill must not claim one.

## Project and page layer

| DSL surface | Status | Verified boundary |
| --- | --- | --- |
| YAML manifest/page filenames | Verified | `pptx.yaml` / `*.pptx.yaml` manifests and `*.page.yaml` pages; JSON syntax accepted inside YAML files; old suffixes and ambiguous directory lookup rejected |
| pptx.yaml v2 manifest, size, ordered page paths | Verified | Exactly one manifest, safe relative page paths, non-empty page list, page files present |
| Theme colors/text styles/table styles | Verified | References must resolve; unknown fields fail |
| Font family / custom web fonts | Supported with boundary | The Python exporter neither provisions remote custom fonts nor embeds fonts. Representative LibreOffice renders lost Chinese glyphs for unavailable/substituted MiSans / Times New Roman; target-consumer verification is required |
| Page background, notes, element order | Verified | Solid/gradient/image backgrounds and notes serialize; array order controls stacking |
| Slide-level fade/none transition | Verified | Root-level transition ordering inspected in generated slide XML |
| Arbitrary PPTX to pptx.yaml | Not provided | pptx.yaml to PPTX is the implemented direction |

## Authoring, publication and review

| Surface | Behavior | Boundary |
| --- | --- | --- |
| `deck create`, `page open/update` | Retain candidates, run geometry and Office preview before publication | Requires local rendering tools; formal YAML carries a CLI-edit reminder, not access control |
| `page insert/split/merge/move/remove` | Modify local page structure and check the resulting page set | Retired sources remain; full-deck PPTX is exported separately |
| Geometry gate | Reject undeclared positive-area intersections and out-of-canvas bounds | Conservative rectangle envelopes; not glyph/ink/overflow detection; no skip flag |
| Native text fit | Measure fonts, sizes, wrapping and required dimensions through LibreOffice before page publication and `deck export` | Horizontal text frames; table/chart labels and image text need separate review; vertical text is unverified |
| Failure repair | Work objects freeze content after geometry failure; three failures suggest splitting | Suggestion is optional; legacy sessions do not have this work-chain rule |
| Version checks | Check source and preview asset dependencies around publication | Recoverable local writes, not isolation from arbitrary external filesystem writers |
| Lock ownership | Kernel-owned locks release on process exit | Persistent lock files must not be deleted; native platform behavior needs platform-specific testing |
| `deck outline` | Model-authored intent with page/asset/appearance/neighbor freshness | Does not grade argument quality or satisfy semantic requirements |
| `gates.hard` / `gates.live` | Separate executable rejection from model requirements and suggestions | A program pass is not semantic or visual acceptance |
| `replace-page` | Preserve non-target slide identities and XML/resource semantics | Full candidate export followed by one-slide transfer; no page-count change |

## Elements

| Element | Status | Verified boundary |
| --- | --- | --- |
| Text | Verified | Explicit line breaks, fixed/proportional paragraph spacing, paragraph margins, inline highlights/decoration/letter spacing and the documented list/inline subset; unsupported list-style CSS is rejected |
| Text `rotation` / `opacity` / `flip` | Rejected | Dynamic OOXML inspection proved these values were dropped by the writer |
| Shape | Verified | All 177 documented preset names generated; custom SVG path requires a valid viewBox/path |
| Line | Verified | Straight/custom point paths, curve modes, borders, and supported arrowheads; invalid/out-of-viewBox points fail |
| Image | Verified | Local/remote/data URLs, fit/crop/crop-shape, borders and shadows; SVG fit uses viewBox or absolute dimensions (ambiguous dimensions rejected); local paths must remain inside the project |
| Nested image fills | Verified | Recursive resolution covers page, element, table-cell/theme-style and other nested image-fill objects; missing/failing images abort export |
| Icon | Supported with boundary | The core PPTX serializes a private `k:icon` extension plus a generic editable fallback shape; standard consumers may show only the fallback. Use an external PNG/SVG for delivery icons |
| Table | Verified | Column/row ratios, cell text/styles, border arrays and merged-cell occupancy; a native OOXML table was inspected |
| Chart: bar/line/area/pie/radar/waterfall | Supported with boundary | Native chart parts and visible marks were observed; exact consumer rendering still requires visual QA |
| Chart: scatter/bubble | Verified | The permanent boundary fixture exports separate `scatterChart` / `bubbleChart` parts, two value axes per chart, exact x/y values, monotonic bubble sizes, and visibly distinct marks in LibreOffice. Target-consumer visual QA is still required for delivery |
| Chart: candlestick/heatmap/treemap/sunburst/sankey | Rejected | Real exports showed missing candlesticks or empty/misleading fallback charts; use external PNG/SVG or a labeled placeholder |

## Animation

| DSL surface | Status | Verified boundary |
| --- | --- | --- |
| Element animation targets and sequencing | Verified | Target IDs, trigger/effect enums and effect-specific required fields are strictly checked |
| Entrance/emphasis/exit/motion-path serialization | Verified | The permanent fixture checks root transition order, target shape IDs, durations, and `animEffect` / `anim` / `animScale` / `animClr` / `animMotion` / `bldLst` nodes in a real export |
| Native playback parity across PowerPoint/WPS/Keynote | Not provided | Requires consumer-specific playback testing |

## Failure policy

- Unknown fields, unsupported enum values, unresolved references, unsafe paths, invalid dimensions/ranges, malformed table merges, inconsistent chart data/encodings, and invalid animation targets are errors.
- Export success is not used as evidence that an input is valid. Validation happens before the Python writer and before output creation.
- Figures, charts, and finished tables should be supplied as user/external PNG/SVG assets; when unavailable, use a clearly labeled placeholder frame. Native chart/table DSL is a compatibility path, not the default production path.
- Browser screenshots, Office/LibreOffice renders, and animation playback are separate evidence layers. OOXML/ZIP inspection alone is not a visual pass.
- A source page edit uses `page open/update`. To update one slide of an existing binary while preserving others, use `replace-page`; whole-ZIP byte equality is not required.

## Evidence retained in this workspace

- Permanent boundary fixture: `tests/core/fixtures/boundary-capabilities/`
- Permanent export/OOXML regression: `tests/core/test_boundary_capabilities.py`
- Runnable authoring example: `skills/ansatz-slide/reference/authoring-start.md`
- Starter export/OOXML regression: `tests/core/test_authoring_start.py`
- Incremental preservation regressions: `tests/core/test_incremental_replace_pptx.py`

Historical scratch reports are not shipped or assumed present. Use retained fixtures and current test runs for reproducible structural checks; a regression pass does not replace target-consumer visual review. See [delivery checks](../skills/ansatz-slide/reference/delivery-checks.md) for claim-specific evidence.
