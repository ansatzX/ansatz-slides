---
name: ansatz-slide
description: Create and edit YAML presentation projects through page work objects, export editable PowerPoint files, and replace selected pages in an existing PPTX. Use for presentation authoring and scoped slide edits; arbitrary PPTX-to-source conversion is not lossless.
---

# ansatz-slide

Deliver the requested presentation and reusable source project. The model authors and reviews the content; the CLI checks schema, geometry and versions before publishing sources. Final visual and argument review remain separate from program acceptance.

## Working rules

Preserve supplied facts, user scope and unrelated work. User templates override visual defaults. Missing evidence stays explicit; do not fabricate results, citations or assets. Resolve consequential ambiguity, otherwise proceed with reasonable assumptions. These instructions grant no additional permissions or mandatory approval steps.

Use the actual installed CLI and available image tools. Do not weaken validation or overwrite a full deck to evade a failed scoped edit. Record only observed checks. Keep working notes in permitted scratch storage, outside the slide content.

## Mathematical notation

Author mathematical expressions and most mathematical symbols in **LaTeX**,
including inline variables, Greek letters, relations, operators and scripts.
Do not build formulas from Unicode glyphs such as α, ≥, ∑ or superscript digits.
For supported editable inline math, write `\(x_i\)` or `\(\alpha \geq 0\)` in
YAML block/single-quoted text (double the backslashes in JSON strings).
For full expressions, use the [LaTeX rendering route](reference/equations.md)
and preserve the `.source.tex`; unsupported native commands are not a reason
to substitute Unicode text. Ordinary prose, punctuation and proper names remain
text. This is an authoring rule, not permission to rewrite unrelated supplied text.

## Choose the needed reference

| Need | Reference |
| --- | --- |
| Environment, installation, renderer dependencies | [Operations](reference/operations.md) |
| First page | [Executable starter](reference/authoring-start.md) |
| Author from supplied material | [Source workflow](reference/source-workflow.md) |
| Create, update or reorder pages | [Work-object CLI](reference/review-cli.md) |
| Look up fields | [Presentation schema](reference/presentation-schema.md) |
| Choose a scenario or named style | [Scenarios](reference/slides_categories.md), [style inventory](reference/design-system-inventory.md), [style boundaries](reference/design-system-runtime.md) |
| Academic talk or substantive academic rewrite | [Academic authoring](reference/academic-authoring.md) |
| Research group report | [Group-report choices](reference/group-report-guide.md) |
| Equation typesetting | [Equations](reference/equations.md) |
| Poster or infographic | [Poster guide](reference/general-poster.md) |
| Check explanation and layout | [Page and deck review](reference/page-and-deck-review.md) |
| Preserve other pages of an existing PPTX | [Page replacement](reference/page-edit.md) |
| Final handoff | [Delivery checks](reference/delivery-checks.md) |

Read only what the task needs. For a new academic talk, understand the argument before layout; a reading note is not automatically a slide outline. A local typography correction does not authorize reauthoring the talk.

## Efficient revision loop

For an existing deck, read only the requested pages and relevant instructions.
Use `ansatz-slide --compact page open PROJECT --page 2 --page 4 --no-preview`
when the old version is already available for visual reference. This opens both
pages in one tool call without rendering old pages again. `textFit: unverified`
means measurement was deferred, never passed. Updates still run all checks and
render the new candidate before publication. Omit `--no-preview` when you need
to see the existing appearance.

Use `--compact` for work commands to avoid repeatedly reading dense matrices and
successful font reports. Source content is included on open; full evidence stays
in the returned `revisionEvidence` file. Read detailed evidence when a failure
needs it. Compact output retains issues, restrictions, live directives and
neighbor freshness. It is a presentation option, not a weaker check.

For an existing deck with several requested page changes, prefer one delivery
command after the combined open: `ansatz-slide deck revise PROJECT --plan
revision.json -o next.pptx`. The plan is a list of `{"work":"WORK_PATH",
"edits":[...]}` with optional `"layout":[...]`. Prefer these local patches over
writing a candidate file. Full `"content":"candidate.page.yaml"` is for an
explicitly requested structural redesign, not routine next-version edits.
Paths are relative to the plan file. The command applies checked edits sequentially,
exports once, renders the actual full PPTX and returns changed-page image paths
plus stage timings. Open those images together and deliver; a second inspect or
manual Office/Poppler conversion is unnecessary unless evidence is missing.
Do not regenerate the whole-deck brief for a visual-only revision.

Reuse existing element IDs, styles and groups. For placement, use `layout`:
`{"kind":"row","items":[["box1","text1"],["box2","text2"]],"bounds":[60,180,820,100]}`
moves groups intact and calculates equal gaps; `column` does the same vertically.
`{"kind":"segments","items":["seg1","seg2"],"bounds":[60,240,820,54],"weights":[2,1]}`
computes weighted bar sizes. Do not hand-calculate every coordinate or introduce
fresh page-generation scripts for these operations. See the local-layout examples
in `reference/review-cli.md`. Only change fields requested by the user; layout
does not silently shrink text, alter styles, or remove content to make it fit.

A revision is NOT an atomic multi-page source write: if a later page fails,
`appliedPages` lists completed source edits and `pages` gives retained work for
repair. Remaining edits stop and the previous delivery PPTX stays untouched.
Repair only the failed/remaining work, then rerun a plan using current references;
do not blindly replay stale applied entries. If all source edits applied but
final rendering failed, use a plan with the latest returned work references
(no-op content is permitted) to retry safely. Final images require model/human
review; rendering success does not certify meaning or PowerPoint/WPS parity.

Prepare all requested changes together. For several edits on one page, use
`page update WORK --edits edits.json`, a list of
`{"element":"title","changes":{"content":{"text":"New title"}}}`.
This creates one checked revision and one new preview. Use `--content` only when
replacing the page structure. Independent pages may be opened in one call and
updated sequentially in one tool invocation; do not run concurrent source writers.
Check each result and stop on failure. Reuse the returned work references; do not
reopen pages just to obtain another reference. Open the changed-page images
together when the runtime permits. Record only affected outline entries; rewrite
the whole-deck brief only when its premise/section argument actually changes.

On text failure read `overflowEdges` and `repairHint`: a negative top/left edge
is not solved merely by enlarging width/height. Inspect paragraph/font layout
instead of repeatedly growing the frame. Never delete content to silence a gate.

## Normal authoring loop

1. Prepare settings, a first-page candidate and project-local assets using the starter. Run `deck create PROJECT --settings FILE --content FILE`.
2. Use the returned `work`, or open requested pages together. Always retain live directives; review neighboring logic when the argument/order changes. Existing-deck visual/text corrections follow the efficient loop above instead of restarting authoring.
3. Batch small changes with `edits` and computed placement with `layout`. Use full `--content` only for a requested structural redesign. Continue with the returned work reference.
4. For a new deck record purpose, audience, central claim and section argument with `deck brief`; keep page intents in `deck outline`. Update these only when their meaning changes. Use `page insert/split/merge/move/remove` when page structure needs to change.
5. Deliver after checking the actual final PPTX previews. `deck revise` already exports and structurally inspects the artifact; do not repeat that tool chain. Open changed-page images together and promptly return the file; prepare extensive logs only if requested.

Formal YAML has a first-line CLI reminder: edit candidates and publish through the CLI instead of directly rewriting existing formal files. The reminder is not a filesystem permission barrier. Page filenames identify sources; manifest order defines page numbers.

Native text is measured with actual font layout before publication; inspect `textFit` for required dimensions, actual fonts and overflow. Table/chart labels and image-contained text still need separate visual review.

Geometry failure retains the candidate and matrices. Only layout changes are then allowed; preserve content and styles. After three consecutive geometry failures, splitting is suggested, not mandatory. Intentional overlaps require specific element pairs and reasons; do not blanket-approve collisions to pass.

Read `context.narrative` during page work. Record explicit user requirements and revisable model proposals separately with `deck directive`, citing their actual sources. Revise or revoke by ID with evidence; never infer revocation from source changes. Resolve `unresolvedDirectives` after source pages are retired. Review the whole argument after structural changes, and affected page intents after premise changes. Preserve narrative/outline metadata with the source handoff.

`gates.hard` reports program restrictions. `gates.live` carries semantic requirements and optional suggestions for the model. The CLI never grades or certifies them. Missing or stale intent calls for review, not an invented program gate. Review affected neighboring logic after a local change; broaden only when shared content or premises require it.

## Export and deliver

```bash
ansatz-slide deck export ./deck -o ./result.pptx --offline --transition none
ansatz-slide inspect ./result.pptx
```

Use the actual project path. Standalone Skill execution replaces `ansatz-slide` with `python <skill>/scripts/ansatz_slide.py` in its environment. `--force` permits authorized output replacement only; it cannot skip checks. `deck export` defaults to no transition; older `export`/`replace-page` default to fade. Academic decks normally omit element animation.

Source updates do not overwrite an existing full-deck PPTX. Export again, or use binary page replacement when preservation of existing non-target slides is required. Fonts are not embedded. Deliver the manifest, referenced pages and assets with the requested PPTX; distinguish structural, visual and semantic checks and identify any unverified layer.
