---
name: ansatz-slide
description: Create and edit YAML presentation projects through page work objects, export editable PowerPoint files, and replace selected pages in an existing PPTX. Use for presentation authoring and scoped slide edits; arbitrary PPTX-to-source conversion is not lossless.
---

# ansatz-slide

Deliver the requested presentation and reusable source project. The model authors and reviews the content; the CLI checks schema, geometry and versions before publishing sources. Final visual and argument review remain separate from program acceptance.

## Working rules

Preserve supplied facts, user scope and unrelated work. User templates override visual defaults. Missing evidence stays explicit; do not fabricate results, citations or assets. Resolve consequential ambiguity, otherwise proceed with reasonable assumptions. These instructions grant no additional permissions or mandatory approval steps.

Use the actual installed CLI and available image tools. Do not weaken validation or overwrite a full deck to evade a failed scoped edit. Record only observed checks. Keep working notes in permitted scratch storage, outside the slide content.

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

## Normal authoring loop

1. Prepare settings, a first-page candidate and project-local assets using the starter. Run `deck create PROJECT --settings FILE --content FILE`.
2. Use the returned `work`, or `page open PROJECT --page N` for an existing page. Read `context.previous/current/next` and open the actual returned preview image.
3. Use `page update WORK --element ID --changes FILE` for a small change, or `--content FILE` for a complete candidate. Continue with the newly returned work reference.
4. Record a short whole-deck purpose, audience, central claim and section argument with `deck brief`; keep page purpose, claim, evidence and connections in `deck outline`. Use `page insert/split/merge/move/remove` when readable content needs a different page arrangement.
5. Export the integrated deck and inspect that exact PPTX before delivery.

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
