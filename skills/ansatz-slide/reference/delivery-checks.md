# Delivery checks

Check the delivered version, not a prior preview. Keep structural validity, visual fidelity, page explanation and deck coherence as separate claims. A successful command or completed checklist does not prove all four.

## Source and artifact

- Deliver the manifest, every referenced page and local asset with the requested PPTX. Preserve sources, units, conditions and qualifications. Disclose remaining remote dependencies.
- Export current inputs and inspect the actual PPTX for page count/order, relationships and required text/assets. Use the [field reference](presentation-schema.md) and executable validator when a construct is uncertain.
- For binary single-page replacement, check the non-target preservation result under [page replacement](page-edit.md).
- `deck export` defaults to no transition; older `export`/`replace-page` default to fade. Check the chosen setting, and review animation playback separately if requested.

## Visual and content review

Open or render the exact final PPTX in the intended consumer when available. Inspect individual pages at readable resolution; a contact sheet is useful for rhythm, not detailed glyph/crop verification. Check complete labels, final text lines, contrast, figure scale and source annotations.

Use [page and deck review](page-and-deck-review.md) to assess both visible reasoning and spatial explanation. For new academic talks and substantive rewrites, also apply [academic authoring](academic-authoring.md): audience fit, evidence-to-claim correspondence and visible limits matter independently of successful export. A local formatting change does not require reauthoring the whole argument.

Re-review affected pages after changes. Shared theme, fonts, images or premises may invalidate more than the edited page. Keep rendered evidence matched to the final artifact. Static images do not establish animation fidelity or native PowerPoint/WPS equivalence.

## Handoff

Identify the requested output and source project, checks actually run, renderer and pages viewed, and unresolved defects or missing checks. Use concise evidence such as “page 6 y-axis label is now fully visible after recropping,” not “all axes checked” without observation.

| State | Meaning |
| --- | --- |
| Passed | Ran on the current artifact and met the stated criterion |
| Failed | Ran and found a concrete defect |
| Not run | No result is claimed |
| Blocked | Required input, tooling or authority is unavailable |

Deliver completed work when useful, stating any unverified layer. Do not conceal a known defect, claim visual acceptance from OOXML alone, or treat model-authored intent as independently approved. No particular report schema or extra human approval is required by this checklist.
