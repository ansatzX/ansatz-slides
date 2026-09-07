# Delivery checks

## 1. Content and source

- Pages answer the agreed reader task and preserve supplied claims. Assumptions, pending assets and limitations are distinguishable from findings.
- Each evidence figure has the labels, units, interpretation and source needed to understand it. Do not crop away a qualification, axis or sample definition.
- Deliver the manifest, referenced page files and local assets together. Where remote dependencies remain, disclose them instead of calling the project completely self-contained/offline.

## 2. Syntax and PPTX structure

- Run the strict validator against the current manifest. A previous pass is invalid after relevant source changes.
- Check the actual exported PPTX ZIP for integrity and its page count/order against the manifest.
- Inspect high-risk objects and relationships in OOXML; confirm that requested text/assets are present rather than relying only on file existence or object counts.
- For the default fade transition, each slide has one root-level `p:transition/p:fade` after `cSld` and optional `clrMapOvr`, before timing/extensions. For `--transition none`, no fade is expected.
- For one-page edits, require the non-target preservation checks in [page-edit.md](page-edit.md).

## 3. Final visual review

Render or open the exact exported/merged PPTX using an available Office consumer. Review every slide individually at sufficient resolution for text and image details. A contact sheet helps compare rhythm and consistency but does not replace individual review.

Check text wrapping, font substitution/missing glyphs, unintended overlap, clipping, crop distortion, labels, contrast and presentation-distance readability. Shorten text or adjust layout before shrinking type. Intentional shape/text overlays are not automatically defects.

After a change, re-export and review affected pages; changes to shared fonts, theme, size or assets require broader review. Keep the final file and its reviewed render matched. Source previews cannot establish final PPTX fidelity. Static renders cannot establish animation playback parity.

## 4. Report only what was checked

| State | Use when |
| --- | --- |
| Passed | Relevant check ran on the current artifact and met its criteria |
| Failed | Check ran and found a defect; identify it and repair or disclose it |
| Not run | Check was not performed; no claim about its result |
| Blocked | Required tooling, input or authority is missing; state what is needed |

The handoff should identify the project/PPTX, the checks actually run, the renderer and pages reviewed where applicable, and any unresolved issues. Do not require a particular JSON report schema or tool API; a concise record with those facts is sufficient. If final visual review cannot run, deliver valid source/PPTX when possible but mark visual QA unverified. Never invent a pass or conceal a known defect.
