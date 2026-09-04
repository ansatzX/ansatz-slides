---
name: ansatz-slide
description: Create or edit PPTD presentation projects and export local PPTX files. Use for slide decks, PowerPoint deliverables, or explicit editable PPTD posters. Supports scoped page replacement; does not provide lossless arbitrary PPTX-to-PPTD conversion.
---

# ansatz-slide

For presentation tasks, produce a self-contained PPTD project and its matching PPTX unless the user requests a different output scope. Explicit image-only poster tasks follow the poster guide. PPTD describes supported page objects; the bundled writer exports them. Do not equate successful export with correct content or visual quality.

## 1. Establish scope and constraints

Read [the execution contract](reference/agent-contract.md). Identify the requested operation, supplied evidence, audience/language, output location, page count if specified, and visual direction. Ask only about missing decisions that materially affect the result; otherwise state a reasonable assumption and proceed.

- Preserve supplied facts and outline scope. External research is not an automatic way to fill pages.
- Host permissions and user authorization govern actions. Do not install global dependencies, automatically download a browser, publish, or overwrite unrelated work.
- Never weaken strict validation or invent facts/assets to satisfy a layout.
- Keep the user's reference files read-only. When using a PPTX as a source, inspect its ZIP media and relationships; do not turn entire slides into image substitutes for editable content.

## 2. Read only the relevant guidance

| Task | Read |
| --- | --- |
| Ordinary page authoring | [Executable starter](reference/authoring-start.md); relevant sections of [PPTD syntax](reference/pptd.md) for additional fields |
| No specified visual system | [Scenario guide](reference/slides_categories.md), then one matching scenario |
| Named preset | [Style runtime contract](reference/design-system-runtime.md), [inventory](reference/design-system-inventory.md), and the selected style only |
| User template/style reference | Inspect its actual pages/assets; user requirements take priority over generic aesthetic defaults |
| Research group report | [Group-report methodology and visual system](reference/group-report-guide.md); a specific user template may override the default visual system |
| Explicit poster/infographic in PPTD | [Poster guide](reference/general-poster.md) |
| Tool invocation or missing dependencies | [Commands and environment](reference/operations.md) |
| Edit one page | [Page-edit procedure](reference/page-edit.md) |

Presets are used only when requested. Their visual prescriptions do not extend DSL syntax or override evidence and edit-scope constraints.

## 3. Prepare content and assets

Assign each page a purpose and main message, then arrange its evidence and explanation. Choose density to fit the audience; do not manufacture content or shrink it to illegibility to fill space.

Figures, charts, diagrams and finished tables come from the user or an external tool. Store them in `media/`; PPTD handles placement, native titles, annotations and source labels. Missing evidence stays explicitly marked as pending. Generated conceptual imagery must not impersonate actual measurements, screenshots or documentary evidence.

Keep local assets inside the project, record their sources where relevant, and avoid overwriting shared assets during a page edit. Prefer `fit: {mode: contain}` for complete evidence. Preserve labels, units and other details needed to interpret it.

## 4. Author and export

Write the manifest and separate `.page` files using the supported subset. Use native text, shapes and lines for page framing/annotations; keep evidence assets external. A shape's text is a separate text element. Choose available Latin/East Asian fonts; fonts are not embedded by the core exporter.

Run strict validation before export. Fix the reported field/path; do not retry unchanged inputs or replace useful evidence merely to pass validation. For a one-page edit, use the scoped procedure rather than exporting over the baseline.

Default export adds fade slide transitions; `--transition none` disables them. Element animations are separate: use only when requested or clearly beneficial for live presentation, and never claim playback verification from a static image. Add speaker notes only when requested.

## 5. Verify and deliver

Follow [delivery checks](reference/delivery-checks.md): inspect the exported PPTX structure and review the exact final file's renders when possible. Browser preview is an optional authoring aid, not final Office verification. Report unavailable checks without inventing a pass.

Deliver clickable paths to the source project and PPTX (manifest separately when useful), plus a concise status of validation, visual review and unresolved gaps. The project must include its referenced pages/assets. If export is blocked, deliver valid source work with the specific blocker. Do not claim features or review stages that were not exercised.

Offer the local editor only when useful; do not require a browser for core export or add unrelated workflow instructions to every final response.
