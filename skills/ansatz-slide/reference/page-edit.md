# Replace one page in an existing PPTX

For source authoring, use [page work objects](review-cli.md). This procedure covers the later binary integration step: transferring one page into an existing PPTX while preserving its other slides. It does not insert, delete or reorder delivered pages.

## Inputs

Use the baseline PPTX, the corresponding full source project, and the target's one-based manifest index. Resolve an ambiguous correspondence before writing. A PPTX alone does not provide editable YAML; reconstruction is a separate task without an arbitrary lossless reverse-conversion guarantee.

## Procedure

1. Preserve the baseline. Open the target with `page open PROJECT --page N`; edit through the returned work reference. Keep non-target sources and shared assets unchanged. Use a new page-specific asset when a figure needs modification.
2. Review the actual returned image and the page's incoming/outgoing reasoning using [page and deck review](page-and-deck-review.md). Do not manually rewrite the manifest to obtain a preview.
3. Integrate into a new output:

```bash
ansatz-slide replace-page --baseline ./baseline.pptx --project ./edited-deck \
  --page 2 -o ./updated.pptx --offline --transition none
```

4. Inspect the preservation report and review the exact merged PPTX. A source preview cannot prove the merged file's fidelity. Record source preservation, package preservation and visual review separately.

The command exports a full candidate, then transplants the selected slide and dependencies. It verifies non-target slide identities, relationships, canonical XML semantics and recursively referenced resources. Whole-ZIP byte equality is not required. Use the full project with the original index, not a one-page preview project.

On failure, keep the baseline and repair the cause; do not substitute a full export over it. `--force` permits replacement of an authorized existing output, not the baseline or unrelated sources. For split/merge/order changes, use source pagination and export a new full deck instead.

## Review scope

A local correction should address a concrete visible or explanatory defect, preserve satisfactory content, and recheck neighboring connections. Shared theme/font/asset changes or a changed premise can require broader review. Final delivery follows [delivery checks](delivery-checks.md).
