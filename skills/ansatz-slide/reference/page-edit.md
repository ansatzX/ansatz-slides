# Editing one page without changing the others

## Inputs and scope

Require the baseline PPTX, its corresponding PPTD project, and the target page's 1-based manifest index. If the correspondence or target is ambiguous, resolve it before writing. This procedure does not insert, delete or reorder pages.

If only PPTX is available, request source or clarify a reconstruction task. The package has no arbitrary reverse-conversion entry point. Do not promise exact preservation through an unverified reconstruction.

## Procedure

1. Preserve the baseline. Record hashes of all non-target `.page` files, the manifest and shared assets before editing.
2. Change only the target `.page` and its exclusive assets. If shared media needs a different appearance, copy it to a new target-specific asset instead of overwriting it. Shared theme/manifest changes require expanded user scope.
3. Validate the project and invoke incremental replacement to a new output path:

```bash
node bin/ansatz-slide.js incremental /absolute/baseline.pptx /absolute/edited-project --page 2 -o /absolute/result.pptx
```

The public CLI can be replaced by the installed Python entry point:

```bash
python3 /absolute/skill/scripts/incremental_replace_pptx.py --baseline /absolute/baseline.pptx --project /absolute/edited-project --page 2 --output /absolute/result.pptx --report /absolute/permitted-scratch/report.json
```

Use an available Python 3.11+ interpreter. The direct entry point uses named arguments; do not copy the public CLI's positional form into it. `--force` is required to overwrite an existing incremental output and should only be used with authorization.

4. Confirm non-target source hashes are unchanged. Inspect the replacement report: non-target slide IDs, relationships and recursively referenced OOXML/resources must retain their semantics.
5. Render/open the final merged PPTX and review the target page. Report source preservation, OOXML preservation and visual review separately.

## Boundaries and failure

The implementation exports a full candidate, then transplants the target dependency closure into the baseline. It is not target-only compilation. Candidate validation or an unavailable asset on another page may therefore block the operation.

If replacement or preservation checks fail, keep the baseline and source edits, report the failure, and do not deliver a full-regeneration substitute as an incremental success. A preservation failure invalidates the candidate output even if a file exists. ZIP timestamps/compression may differ; the promise concerns non-target OOXML semantics, not byte-identical ZIP archives.
