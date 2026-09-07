# Editing one page without changing the others

## Inputs and scope

Require the baseline PPTX, its corresponding pptx.yaml project, and the target page's 1-based manifest index. If the correspondence or target is ambiguous, resolve it before writing. This procedure does not insert, delete or reorder pages.

If only PPTX is available, request source or clarify a reconstruction task. The package has no arbitrary reverse-conversion entry point. Do not promise exact preservation through an unverified reconstruction.

## Procedure

1. Preserve the baseline. Record hashes of all non-target `.page.yaml` files, the manifest and shared assets before editing.
2. Change only the target `.page.yaml` and its exclusive assets. If shared media needs a different appearance, copy it to a new target-specific asset instead of overwriting it. Shared theme/manifest changes require expanded user scope.
3. Validate the project and invoke incremental replacement to a new output path:

```bash
uv run --frozen ansatz-slide replace-page --baseline /absolute/baseline.pptx --project /absolute/edited-project --page 2 -o /absolute/result.pptx --offline
```

For an installed skill, use `python3` with
`/absolute/skill/scripts/ansatz_slide.py`. Use Python 3.11+ with PyYAML for YAML
inputs; JSON inputs need only the standard library. Both candidate generation
and replacement run in Python. `--force` replaces an existing incremental
output and requires authorization; the baseline remains protected.

4. Confirm non-target source hashes are unchanged. Inspect the replacement report: non-target slide IDs, relationships and recursively referenced OOXML/resources must retain their semantics.
5. Render/open the final merged PPTX and review the target page. Report source preservation, OOXML preservation and visual review separately.

## Boundaries and failure

The implementation exports a full candidate, then transplants the target dependency closure into the baseline. It is not target-only compilation. Candidate validation or an unavailable asset on another page may therefore block the operation.

If replacement or preservation checks fail, keep the baseline and source edits, report the failure, and do not deliver a full-regeneration substitute as an incremental success. A preservation failure invalidates the candidate output even if a file exists. ZIP timestamps/compression may differ; the promise concerns non-target OOXML semantics, not byte-identical ZIP archives.
