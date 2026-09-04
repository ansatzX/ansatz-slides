# Next-run handoff - 2026-09-04

This is the restart point for the current functional-development phase. Do not repeat the full audit unless code or the bundled writer changes.

## User decisions that remain authoritative

- Project/package/CLI/skill name: `ansatz-slide`.
- Core direction is PPTD to PPTX. Do not claim arbitrary PPTX to PPTD conversion.
- Invalid or writer-dropped DSL must fail before output; silent downgrade is unacceptable.
- `candlestick`, `heatmap`, `treemap`, `sunburst`, and `sankey` should be external PNG/SVG figures or labeled placeholders, not chart DSL.
- Figures, charts, and finished tables are made by dedicated tools or supplied by the user; PPTD/PPTX only arranges the resulting assets and adds titles/annotations/sources. Native chart/table DSL is compatibility-only, not the default production path.
- A one-page edit must preserve non-target pages at OOXML semantic level. Whole-ZIP byte identity is not required.
- Font embedding is not a default requirement and must never be claimed without inspecting font parts.
- The no-embedding/cross-Office font boundary is an accepted documented limitation for now; do not start a font-embedding implementation without a new request.
- Core export is pure Node. Python is transitional/QA-only and locked with uv.
- Browser QA reuses a system Chrome/Chromium/Edge; never download Chromium.
- SBOM/license aggregation is deferred during functional development.

## Implemented in the working tree

- Strict executable PPTD validator integrated into Node and Python paths.
- Known invalid inputs, dropped text transforms, and five broken chart types are rejected.
- Pure Node 24 `ansatz-slide validate` and `ansatz-slide export` commands.
- `ansatz-slide incremental` OOXML dependency-closure replacement and semantic verifier.
- Recursive nested image-fill collection/resolution; missing or failed images abort export.
- No automatic global npm/pip install; Python scratch data uses repository `./tmp`.
- npm + `package-lock.json`; uv + `pyproject.toml`/`uv.lock`; installed skill vendors YAML and carries uv locks.
- Full package/CLI/skill-facing rename to `ansatz-slide`. The outer workspace directory still has the legacy physical name; this handoff records that path explicitly, but shipped identifiers do not retain it.
- Guide-deck methodology and visual system are separate sections in `skills/ansatz-slide/reference/group-report-guide.md`.
- Durable support/dependency summaries: `docs/DSL_SUPPORT_MATRIX.md` and `docs/DEPENDENCIES.md`.
- All 88 pre-existing Markdown files were audited for current runtime claims; central README, skill, font, category, theme, changelog, editor, DSL, dependency, and handoff documentation was corrected without duplicating runtime rules into every visual preset.
- Durable local-link checker: `.scripts/20260904-ansatz-slide-check-markdown-links.py`; its final run found zero missing local targets.
- Bundled examples migrated away from stale invalid table/rich-text syntax.
- Permanent boundary fixture and OOXML E2E regression for separate scatter/bubble charts, animation targets/effects, root transitions, and the current icon-extension/fallback behavior.

## Verification already completed

- `npm test`: 26 passed.
- `uv run --frozen --extra qa python -m unittest discover -s skills/ansatz-slide/tests -v`: 24 passed.
- Skill quick validation: passed.
- Documentation link audit: 88 Markdown files checked, zero missing local targets after removing the duplicate English README.
- Three real pure-Node exports: 18 + 8 + 8 slides under `tmp/final-validation/`.
- ZIP integrity passed for all three; observed slide counts are 18/8/8.
- DJI slide 17 contains one native table, 12 rows, and 48 cell tags.
- Animated Xiaomi slide 1 contains both timing and root transition XML.
- Real unsupported-chart export failed before output, and `tmp/final-validation/must-not-exist.pptx` was not created.
- Real `incremental` CLI replacement report: `tmp/incremental-fixture/reports/cli-incremental.json`; target changed, non-target pages retained IDs/rIds/canonical semantics and raw associated resources.
- Real npm tarball was about 11.1 MB compressed / 21.7 MB unpacked; local tarball install, pure export, skill copy, vendored YAML, and uv lock copy all passed. No Chromium is bundled.

## Evidence paths

- Static audit: `tmp/static-audit/final-report.txt`
- Dynamic DSL/OOXML audit: `tmp/runtime-matrix/final-report.txt`
- Earlier guide/runtime visual audit: `tmp/visual-verifier/final-report.txt`
- Final exports: `tmp/final-validation/*.pptx`
- Final slide renders: `tmp/final-validation/visual/`
- Luna-generated 34-slide renders: `tmp/final-validation/visual/`
- Visual blocker summary: `tmp/final-validation/visual-blocker.md`
- Luna visual verification produced the retained renders and blocker summary; no separate long-form narrative was required for the functional gate.
- Dedicated boundary export and LibreOffice render: `tmp/boundary-hardening/`; the scatter diamonds and monotonically growing bubbles are visible, while the icon renders as the documented generic circle fallback.
- State nodes: `.state-machine/root.md` and `.state-machine/luna_visual_final.md`

## Remaining work after restart

1. Decide whether the `icon` DSL should remain browser-preview/private-extension compatible, be converted to a packaged PNG/SVG fallback, or be rejected by the core exporter. Rejecting it immediately would require migrating existing examples and is a user-gated compatibility change.
2. Native PowerPoint/WPS/Keynote playback parity remains outside automated static regression. Test it only when a delivery contract requires that consumer.
3. Run the final compact regression commands below again only after additional source changes.
4. Review `git status` carefully. The directory rename appears as old-tree deletion plus new untracked tree until staged; do not reset it. Preserve the user's pre-existing `.gitignore` changes and untracked `AGENTS.md`.
5. Do not commit/publish or rename the outer workspace directory without explicit user instruction.

## Final regression commands

```bash
TMPDIR="$PWD/tmp/test-tmp" npm test
TMPDIR="$PWD/tmp/test-tmp" UV_CACHE_DIR="$PWD/tmp/uv-cache" \
  uv run --frozen --extra qa python -m unittest discover -s skills/ansatz-slide/tests -v
TMPDIR="$PWD/tmp/test-tmp" UV_CACHE_DIR="$PWD/tmp/uv-cache" \
  uv run --frozen python /Users/ansatz/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/ansatz-slide
git diff --check
```
