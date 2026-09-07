---
name: ansatz-slide
description: Create and edit YAML presentation projects, export editable PowerPoint files, and replace selected pages in an existing PPTX. Use for presentation authoring and scoped slide edits; arbitrary PPTX-to-source conversion is not lossless.
---

# ansatz-slide

Produce a YAML source project and its matching PPTX, within the user's requested scope. The Python CLI validates sources, exports PPTX, inspects package structure, and replaces a selected page. Content preparation and final visual review are separate parts of the task.

## Choose the relevant guidance

Read only the references needed for the operation. All paths below are relative to this Skill directory.

| Need | Reference |
| --- | --- |
| Facts, scope and conflicting requirements | [Execution contract](reference/agent-contract.md) |
| Turn text, data and images into a source project | [Source workflow](reference/source-workflow.md) |
| Start authoring or look up supported fields | [Executable starter](reference/authoring-start.md), then [presentation schema](reference/presentation-schema.md) |
| Choose a layout approach without a named theme | [Scenario guide](reference/slides_categories.md) and one matching scenario |
| Apply a requested theme | [Style contract](reference/design-system-runtime.md), [inventory](reference/design-system-inventory.md), and the selected definition |
| Prepare a research group report | [Group-report guide](reference/group-report-guide.md) |
| Create an explicitly requested poster or infographic | [Poster guide](reference/general-poster.md) |
| Set up dependencies or invoke commands | [Operations](reference/operations.md) |
| Change one page | [Page-edit procedure](reference/page-edit.md) |
| Check and deliver the result | [Delivery checks](reference/delivery-checks.md) |

User templates and supplied facts take priority over general style defaults. Use presets when requested; resolve a theme ID through the inventory and do not combine it with a same-ID alternate unless that alternate is explicitly selected.

## Source project

Use `pptx.yaml` or a descriptive `*.pptx.yaml` as the manifest, `pages/*.page.yaml` for pages, and `media/` for local assets. Directory input requires one matching manifest at the project root; specify its path when there are multiple. YAML and JSON syntax are supported inside these files.

Assign each page a purpose and organize the supplied evidence around it. Use native text, shapes and lines for framing and annotations; shape text is a separate text element. For native charts or tables, check the supported fields before authoring. Supplied figures and externally prepared complex charts or tables can be placed as images, with their labels, units and sources preserved. Such images do not become editable data objects in PowerPoint.

Keep local assets within the project. Do not replace missing evidence with invented measurements or misleading illustrations. Select fonts available in the target viewing environment; the exporter does not embed them.

## Validate, export and inspect

Run these commands in the project's Python environment. For an installed standalone Skill, replace `ansatz-slide` with `python <skill-directory>/scripts/ansatz_slide.py`. See [operations](reference/operations.md) for environment setup.

```bash
ansatz-slide validate ./deck/pptx.yaml
ansatz-slide export ./deck/pptx.yaml -o ./result.pptx --offline --transition none
ansatz-slide inspect ./result.pptx
```

Export validates the source before writing. Fix reported fields and paths rather than weakening validation. `--offline` rejects remote image resources. Existing output requires `--force`; use it only when overwriting that file is authorized.

The example disables slide transitions. Without `--transition none`, export defaults to fade. Element animations are configured separately; academic decks default to no element animations. Add speaker notes when requested.

## Replace a page

Read the page-edit procedure before changing a page. Preserve the baseline PPTX and keep source edits within the selected page and its dedicated assets.

```bash
ansatz-slide replace-page --baseline ./baseline.pptx --project ./edited-deck \
  --page 2 -o ./updated.pptx --offline --transition none
```

Page numbers are one-based. The command exports a complete candidate, transfers the selected page and its dependencies, and checks that other pages retain their semantics. It does not compile only the selected page. A failed replacement must not be bypassed by overwriting the baseline with a full export.

## Deliver with evidence

Inspect the final PPTX and review that exact file in the target presentation software when available. Package checks do not establish layout, font or animation fidelity; source previews and theme thumbnails do not replace final-file review.

Deliver the requested PPTX and reusable source project, including referenced pages and assets. State which validation and visual checks were completed and any unresolved gaps. If a required tool or asset is unavailable, preserve completed source work and identify the concrete blocker without claiming a successful export or visual review.
