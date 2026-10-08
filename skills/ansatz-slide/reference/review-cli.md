# Page work interface

The model chooses content and layout. The CLI retains the candidate, checks its
bounds, protects source versions, renders and publishes. A work reference carries
the version internally; do not pass a separate token or manage preview folders.

## Create and open

Write `settings.yaml` containing `version: v2`, `size: [960, 540]`, and optional
title/theme/customFonts; omit page paths. Author one `.page.yaml` candidate.

```bash
ansatz-slide deck create ./deck --settings ./settings.yaml --content ./first.page.yaml
ansatz-slide page open ./deck --page 1
```

Use a new project or an existing directory containing its assets but no manifest.
The CLI retains the first candidate internally. It publishes `pptx.yaml` and a
page source only after checks and preview succeed. On failure, use the returned
work reference to repair that candidate; do not restart project creation.

`page open` returns the selected page, its purpose/claim/evidence when recorded,
related adjacent outline entries, exact compressed matrices and preview paths.
It does not return other pages' body content. Programmatic loading can still read
the whole project to validate sources. Paths are not delivered image pixels:
open the returned image with the runtime image tool. Provider-specific image
injection is outside this CLI.

## Optional compact / multi-page read

`ansatz-slide --compact page open PROJECT --page 2 --page 4 --no-preview`
returns `pages`, each with its own work reference. A single `--page` keeps the
single-result shape. `--no-preview` is read-only: it defers old-page text
measurement and image rendering, marks text unverified, and never skips update
checks. Source/asset version guards remain active. Invalid schema/geometry still
blocks. A multi-page open is a set of reads, not a multi-page write transaction.

`--compact` is a global option placed before `page`. The default response and
Python API are unchanged. Compact output omits inline matrix payloads and passed
text-element detail, retains source content for read/blocked results, and omits
redundant page content after successful publication. Full saved evidence is at
`revisionEvidence`; on conflicts it describes the historical revision, while
current status/issues/directives remain inline and authoritative. All preview
paths, geometry failure details, gates and narrative context remain available.

## Update and repair

Use the exact `work` returned by the preceding operation:

```bash
ansatz-slide page update WORK --element body --changes ./fields.yaml
ansatz-slide page update WORK --content ./candidate.page.yaml
ansatz-slide --compact page update WORK --edits ./edits.json
ansatz-slide page update WORK
```

`--edits` takes a nonempty list of objects with exactly `element` and `changes`.
Patches are applied in order to one in-memory candidate, then validated and
rendered once. Any invalid patch rejects the operation before publication; any
failed gate retains the combined candidate. It cannot be combined with
`--content` or `--element`. Layout-only repair restrictions still apply to every
patch. This is atomic at the existing single-page publication boundary.

The last form retries the retained candidate, for example after a renderer becomes
available. To apply changes made in the returned `editable` file, pass that path
with `--content`; retry alone uses the recorded candidate. Never edit record.json
or head.json. Nested element objects merge; arrays replace. Whole-page changes
replace one candidate, not the deck. Old work references reject updates after a
new revision is returned, including a blocked revision. External source/asset
changes require reopening, preserving the old candidate for deliberate rebase.

The result is a `page-work-v1` object:

| Field | Meaning |
|---|---|
| `work` | Revision-bound path to use for the next update |
| `status` | `ready`, `applied`, `blocked`, `conflict`; command-level failures may return `error` |
| `applied` | Whether the requested source change was published |
| `candidates` | Full retained candidate pages, editable paths, matrices, previews |
| `issues` | Candidate index, error kind and concrete explanation |
| `context` | Explicit `previous`, `current`, `next` page logic, with freshness flags |
| `gates.hard` | Program-owned blocking issues and active restrictions |
| `gates.live` | Model-owned semantic requirements and optional suggestions; not evaluated by CLI |
| `next` | Next command and allowed input forms |

`ready` means read without publishing; `blocked` keeps the candidate and leaves
sources untouched. Check `applied` separately: failure to assemble a post-write
preview/context must not be interpreted as an unapplied source change. `conflict`
rejects an outdated reference. Inspect the new image to judge readability and
meaning; passing geometry is not visual or scientific acceptance. A command-level `error` may report `applied: null` when publication state is unknown; reopen and inspect current sources before retrying.

## Geometry failure: layout-only repair and split guidance

After a candidate fails geometry, `layoutOnly` is true: updates may change only
bounds, rotation and element ordering. Content, font/style fields, image sources,
elements and overlap exemptions stay frozen. A rejected non-layout update leaves
the retained candidate and work reference unchanged; it does not count as another
geometry attempt. Use the same work reference to submit a layout correction.

`geometryFailures` counts consecutive failed geometry checks for each candidate
within the work chain (including its initial check). A passing geometry check
resets it, even if rendering then fails. On the third and subsequent failures,
`guidance` explicitly suggests that the page may be too crowded and may need
splitting; this is a suggestion, not an automatic content rewrite or forced split.

A blocked single-page work object can use `page split`, including before the
first formal manifest exists. That repair must redistribute all original
elements without deleting, duplicating or rewriting their content/styles; notes
are retained. Once the new pages pass, normal content editing is available again.
For a structural operation blocked by another source page, `blockingPages`
returns that page's geometry and matrices so the model can open and repair it.

## Matrix evidence is returned, not merely linked

Each candidate's `geometry.matrices` contains both `occupancy` (0/1) and `counts`
(number of occupying rectangles). Encoding is `row-bands-rle-v1`: each band has a
start row, repetition count, and `[value, length]` runs. Expand runs into one row
and repeat that row. Every cell is represented, with no lossy reduction; shape,
cell size, origin and index convention accompany the data. Work-object matrices
use one cell per canvas unit, limited to four million cells. Larger grids block
with an explicit diagnostic rather than silently decreasing resolution.

`conflictRegions` includes element IDs and a directly expanded count matrix for
each undeclared intersection. Samples are limited to 32 by 32 cells and explicitly
marked truncated with the full region shape; the complete RLE matrices remain
available in the same response. PNGs and gzip TSV artifacts are also retained.

Bounds overlapping at positive area require explicit `allowedOverlaps` pairs
with nonempty reasons in the page source. Out-of-canvas elements are blocked.
Use pair declarations only for intended layering, never blanket exemptions.
Rotation uses conservative rectangular envelopes; text ink/overflow, shadows and
transparency are not measured. Fractional cell contact alone is not geometric
overlap. Missing/malformed geometry cannot yield a valid matrix; the candidate
and validation issue are retained instead.

### Standalone geometry diagnostic

```bash
ansatz-slide page check-overlap --project ./deck --page 2 --output ./work/geometry-2
```

Use a new output directory. This requires no Office tools and writes `report.json`,
`occupancy.tsv.gz` (0/1), `counts.tsv.gz`, `occupancy.png` and `overlap.png`.
Matrices are indexed `[y][x]`, origin top-left. The standalone `--cell-size`
option changes resolution; ordinary work objects retain the exact one-unit grid.
Legacy preview artifacts can coarsen canvases longer than 2000 units; their
reported `cellSize` is authoritative. More than four million cells is rejected.

An intended pair declaration belongs in the candidate page:

```yaml
allowedOverlaps:
  - elements: [frame, label]
    reason: The label sits inside its background frame.
```

IDs must exist and differ. Duplicate pairs, wildcards and empty reasons are
rejected. This permits only the stated pair, not off-canvas content or other
collisions. Zero-area lines are allowed; other zero-area elements are invalid.
Use page background for full-canvas fills when appropriate.

## Measure text before accepting its frame

After declared geometry passes, page previews measure native horizontal text
using LibreOffice and Poppler. The probe retains each text frame's width, fonts,
font sizes, run styles, wrap setting, paragraph spacing and line spacing, but
expands height to reveal text that the original frame could clip. PDF text
coordinates determine the occupied extent. This is not a character-count estimate.

`textFit` reports element IDs, requested styles, fonts actually present in the
rendered PDF, measured bounds, required width/height, and overflow or unverified
reasons. A font substitution is visible in `renderedFonts`; a local measurement
is not a promise of the same result with different fonts or another Office app.
Overflow or unmeasurable native text prevents publication while retaining work.
Repair the candidate and retry. A text-fit failure by itself does not freeze font
fields; existing geometry failures still enforce their separate layout-only rule.

```bash
ansatz-slide page check-text --project ./deck --page 2 --output ./work/text-2
```

Use a new output directory. It retains the probe PPTX/PDF, text bounds and
`text-fit.json`; failure exits nonzero. Page work responses carry measurement
results, and `deck export` measures the same loaded text it will serialize before
replacing the output. Missing LibreOffice, `pdftotext` or `pdffonts` is a blocker,
not a text-fit pass. No automatic font shrinking or content deletion is performed.

Scope is explicit: horizontal native text and emitted rich text are measured.
Vertical text and native Office Math remain unverified and block this gate.
Tables receive a separate consumer silhouette/expansion check; chart labels
remain unmeasured. Image-contained text is not native text. All require visual review. Probes have
finite limits and report unverified when reached. Word extents do not prove glyph
fidelity or reading quality. `validate`, legacy `export` and the low-level Python
writer retain their schema/geometry contracts; use `deck export` for this text gate.

## Flexible pagination

```bash
ansatz-slide page insert WORK --content ./new.page.yaml --position after
ansatz-slide page split WORK --content ./a.page.yaml --content ./b.page.yaml
ansatz-slide page merge WORK --next ADJACENT_WORK --content ./combined.page.yaml
ansatz-slide page move WORK --anchor OTHER_WORK --position before
ansatz-slide page remove WORK
```

For merge/move, open the other page first. Pending work must be repaired or
reopened before another structural operation, except a content-preserving repair
split of a geometrically blocked single page. A blocked insert/split/
merge retains all operation candidates. Repair candidate 2, for example:

```bash
ansatz-slide page update WORK --candidate 2 --element body --changes ./fields.yaml
```

This retries the same structural operation after correction. A successful result
returns a primary page work object for continuing edits; `operationCandidates`
retains the other submitted pages/evidence when applicable. Source filenames
identify pages; manifest ordering determines page numbers. Removed/retired source
files remain on disk. All resulting pages pass geometry before manifest writes.

## Model-authored outline

```bash
ansatz-slide deck outline ./deck
ansatz-slide deck outline ./deck --page 1 --content ./intent.yaml
```

Intent accepts `purpose`, `claim`, `previousConnection`, `nextConnection` strings
and `evidence` as a list of source descriptions. The older combined `connection`
string remains accepted. `requirements` and `suggestions` are separate lists of
nonempty text. An update replaces that page's intent, so send all fields to retain. The model writes these; the CLI does not infer an
argument from titles. Outline entries attach to source paths and survive moves.
They become `needsReview` after page edits, referenced local asset changes, canvas/theme/custom-font changes, or neighbor identity/dependency changes; inserted/split/merged sources have
no confirmed intent until the model supplies it. Retired entries remain visible
in the outline's retired-source list. Updates record one page's current intent,
so unrelated entries are preserved. Semantic consistency is still model judgment.

## Hard gates and live constraints

Every page work response separates two responsibilities:

- `gates.hard`: the program checks source versions/scope, schema/resources,
  geometry, layout-only repair and rendering. Actual `blockingIssues` explain
  rejections. `activeRestrictions` describes candidate-specific layout freezes.
  `applied` reports publication, not semantic quality.
- `gates.live.requirements`: mandatory semantic instructions for the model to
  honor; each carries its page role, source and freshness. They do not execute as
  program conditions and are never automatically marked satisfied.
- `gates.live.suggestions`: optional model decisions, including crowding/split
  advice after three failures. The model can choose another valid layout instead.

For example, store an intent using `deck outline PROJECT --page N --content FILE`:

```yaml
purpose: Explain why the method addresses the preceding limitation.
claim: The method separates the two effects.
evidence:
  - Figure 2, supplied measurement and caption.
previousConnection: Start from the ambiguity established on the previous page.
nextConnection: Prepare the interpretation of the following comparison.
requirements:
  - Explain the causal step before stating the conclusion.
  - Identify which observation supports each claimed effect.
suggestions:
  - Consider a side-by-side explanation if the shared axes remain readable.
```

`context.previous/current/next` each contains page purpose, claim, evidence and
connections through its model-authored `intent`. Only the current page body is
expanded. Missing neighbors are null. Missing intent remains null rather than a
title-derived substitute. `relationNeedsReview` flags changed neighbors, including
legacy intent without a neighbor snapshot. Freshness is a model review prompt,
not a hard gate. A model semantic requirement is not optional merely because the
CLI cannot evaluate it. Do not treat successful geometry/export as satisfying it.

## Export

```bash
ansatz-slide deck export ./deck -o ./result.pptx --offline
ansatz-slide inspect ./result.pptx
```

Deck export defaults to no transition and always rechecks current sources;
`--force` authorizes output replacement only, not bypassing geometry. Per-page
updates do not overwrite a full-deck PPTX. Review the final exported artifact.
The older `export`, `page check/edit/patch` session/token commands, `deck check`
and draft-manifest creation remain [compatibility interfaces](review-cli-legacy.md).
New workflows should use work objects consistently. `page check-overlap` remains
an independent read-only diagnostic and is not an extra required workflow step.

## Recovery and source ownership

Work state lives under `.ansatz/work` and outline intent under `.ansatz/outline.json`.
These are local runtime artifacts; source pages and the manifest remain the
presentation inputs. Retained work/backup files are not automatically deleted.
A failed structural publication can retain new unreferenced page files; inspect
them with the recovery artifacts before any cleanup.
Filesystem writes by unrelated programs and process crashes are not a database
transaction; reopen sources after an interrupted operation and inspect retained
candidates/recovery files rather than assuming a failed process means no write.
Locks are owned by the operating system and released when the process exits,
including abnormal termination. The persistent `.lock` files are coordination
inodes, not evidence of a live owner; do not delete them. An active owner causes
an immediate retryable conflict. After a crash, reopen the page and continue.
Older installed CLI versions must finish before switching to this locking protocol.

Publication rechecks the local asset hashes associated with every preview before
and after writing. A detected change rejects the operation and retains recovery
files; it does not accept an unpreviewed image version. Deck creation checks all
reserved manifest names (`pptx.yaml` and `*.pptx.yaml`) on retries and publication.
Old outline entries without dependency tokens require model review once; subsequent
entries track local asset and appearance dependencies as well as page content.

Formal manifest/page YAML starts with a reminder to use `ansatz-slide` for existing
source edits. Candidates and JSON state do not have that header. The reminder
reduces accidental edits; it does not restrict filesystem permissions. Use a YAML
parser for commented sources. Untouched imported files remain unchanged and gain
the header on their next CLI write.


## Whole-deck argument and attributed directives

Use `deck brief PROJECT --content brief.yaml` to record the model-authored whole-deck argument. It appears under `context.narrative.brief` during page work, alongside the existing previous/current/next page logic. Read the current state with `deck brief PROJECT`.

```yaml
purpose: Explain when the result holds
audience: Research group
centralClaim: The improvement depends on the stated experimental conditions
sections:
  - id: evidence
    claim: Establish the result and its limitations
    sources: [1.page.yaml]
```

Use actual source filenames and cover every current page across the sections. A section may cover multiple pages. Keep the brief short enough to remain useful during local editing. It is a model-authored argument, not a certified summary of user intent.

The CLI records source/asset dependencies and manifest order. Source changes mark the affected sections for review; insertion, splitting, merging, removal and reordering mark the structure for review. Updating one section's argument marks its page intents for review. Changes to purpose, audience or central claim affect all page intents. Re-recording the identical brief after review does not invalidate otherwise current page intents. Revisit the actual argument before recording an updated brief; freshness does not certify coherence.

Use `deck directive PROJECT --content directive.yaml` for an attributed requirement or proposal:

```yaml
id: preserve-limitations
kind: user_requirement
text: Preserve the stated limitations
source:
  reference: path-or-message-reference-to-the-actual-instruction
  quote: Preserve the stated limitations
scope: [1.page.yaml]
```

Replace the illustrative reference/quote with evidence actually supplied by the user. `kind` is either `user_requirement` or `model_proposal`; `scope` is `deck` or a nonempty list of current source filenames. Model proposals cite their authored plan or rationale. The CLI records attribution supplied by the caller; it cannot authenticate a human or prove that the quote supports the paraphrase. Never label an inferred preference as an explicit user requirement. Existing `deck outline` requirements remain labeled model proposals; they are not automatically promoted to user requirements.

Writing the same ID revises its text, evidence or scope and preserves the preceding revision. An ID cannot change origin kind. Record an explicit revocation with:

```bash
ansatz-slide deck directive ./deck --revoke preserve-limitations --source actual-instruction-reference --quote 'Actual revocation wording'
ansatz-slide deck directive ./deck --history
```

Revoked entries disappear from current requirements while their source and before/after history remain in `.ansatz/narrative.json`. Do not revoke a user requirement merely because the layout is difficult. Source changes request review and never revoke a requirement. If a scoped source is retired by a split/merge/removal, its active directive remains visible in `unresolvedDirectives` until its scope is explicitly revised or it is revoked with evidence. Page indices moving do not change source-based scope.

`gates.live.userRequirements` and `gates.live.modelProposals` separate explicit attributed requirements from revisable plans. `gates.facts` identifies the program-produced evidence fields and their candidate/work state; these measurements do not certify semantic acceptance. The existing `gates.live.requirements` field remains for compatibility and carries origin labels. None of these semantic records introduce a new program publication gate.

Keep `.ansatz/narrative.json` and `.ansatz/outline.json` with the source project when its authoring context must survive handoff. Historical evidence is read on demand with `--history`; default reads return active records. Candidate, matrix and typography payloads retain their existing format; this feature does not implement response compression.


## One-command multi-page revision and final delivery

After opening target pages, write a JSON/YAML plan. Relative paths resolve against
the plan file, not the working directory:

```json
[
  {"work":"/absolute/returned/work-2", "content":"page2.page.yaml"},
  {"work":"/absolute/returned/work-4", "edits":[
    {"element":"title", "changes":{"content":{"text":"Updated title"}}}
  ]}
]
```

```bash
ansatz-slide deck revise ./deck --plan ./revision.json -o ./next.pptx
```

Only existing edit work from this project is accepted; each page appears once.
All work references and patch syntax are checked before the first source write.
Candidates are then applied through normal work updates, including pending
layout-only restrictions, text measurement, preview and version guards. A later
failure stops the plan, retains earlier applied source pages, returns their
current work references and leaves any existing output PPTX untouched.
`appliedPages` and `exported` describe these two distinct effects explicitly.
This command is sequential orchestration, not an atomic whole-deck edit.

The full candidate PPTX is exported offline with no slide transition, inspected
by the normal exporter, and rendered by LibreOffice/Poppler before publication.
It is staged under `.ansatz/deliveries/`; output replacement requires `--force`.
Source changes detected during delivery block final publication. The result
includes `preview.changedPageImages`, all page images, `timings`, and a persistent
`report`. These previews render the actual output bytes. Open the changed-page
images; do not run a duplicate export/inspect/render chain just to get them.
An unchanged source page can be included with its latest work and existing
content to retry delivery after a renderer failure. Retained sources/work and
staging remain available for recovery. Fonts and native PowerPoint/WPS rendering
are still outside the automatic verification boundary.

Text measurement preserves middle/bottom alignment in an original-height probe
and also measures an expanded top-aligned probe to expose hidden lines. A
negative top in the expanded probe alone is not an overflow of a centered frame.
Do not insert blank lines merely to compensate for the measurement origin;
use the reported actual-frame bounds and preserve the intended alignment.

## Local edits and calculated layout

A next-version edit should preserve the existing page rather than reserialize it
from scratch. A plan can combine `edits` (applied first) and `layout` in one check:

```json
[
  {
    "work": "CURRENT_WORK",
    "edits": [{"element":"take","changes":{"content":{"text":"Updated takeaway"}}}],
    "layout": [{"kind":"row","items":[["box1","text1"],["box2","text2"]],"bounds":[60,180,820,100]}]
  },
  {
    "work": "OTHER_CURRENT_WORK",
    "layout": [{"kind":"segments","items":["seg1","seg2","seg3","seg4"],"bounds":[66,236,820,54],"weights":[1.18,1.11,0.11,0.58]}]
  }
]
```

Use with `ansatz-slide --compact deck revise PROJECT --plan plan.json -o next.pptx`.
For a single page, `page update WORK --layout layout.json` accepts the operation
list and can combine it with `--edits edits.json`. It cannot combine layout with
full `--content` or single `--element`; use `edits` for a mixed update.

- `row` / `column`: `items` are IDs or groups of IDs. Translate each group without
  changing its element sizes, internal offsets, order, text, or styles. `bounds`
  is the available region. Omitted `gap` distributes remaining space evenly;
  an explicit nonnegative gap packs from the region start. Cross-axis `align`
  is `start`, `center` (default), or `end`. Groups too large for the region fail;
  the operation never silently scales them or shrinks fonts.
- `segments`: individual shape IDs, one positive finite `weights` value per shape.
  Divides the region proportionally along `axis` (`x` default, or `y`), with
  optional nonnegative `gap` (default zero). Only bounds change. Labels are
  separate elements: patch/arrange them explicitly if needed; no data/text is
  inferred or invented from the weights.
- All referenced IDs must exist and occur once per operation. Rotated elements
  require explicit bounds edits. Unknown options, nonfinite values, insufficient
  space, and invalid weights are rejected before publication. Operations run
  sequentially on a candidate copy. Unreferenced elements and page metadata stay
  unchanged. Existing geometry/text checks and layout-only failure restrictions
  still apply; these operations cannot authorize content changes or bypass gates.

For a local iteration, open requested pages once, author this small plan, execute
one delivery command, inspect the returned changed-page images, and return the
PPTX. Do not regenerate the deck brief, source pages, or a custom layout script
for a wording/spacing change. A structural redesign may still need full content.

Revision preflight protects local images introduced by **every candidate**, as well
as the original sources/assets and plan files. These assets cannot be delivery
output paths; a content change during update/export/final render blocks delivery.
The source edits already listed in `appliedPages` remain applied on such a failure.

### Rendering failures and evidence boundaries

After an execution/rendering failure, read `issues[].diagnostic` for the local
traceback. Repair the returned candidate with `page update <returned-work>
--content FILE`; a failed insertion retains its insertion operation. Use the
returned work reference: operations that reach candidate processing supersede
older references, while early rejections may retain the same one. For source conflicts use the stable resume/rebase commands below; reopen only
to explicitly abandon a pending candidate or to rebuild both merge/move anchors.

Text measurement now checks extracted text against source as well as occupied
bounds. A mismatch blocks publication and needs font/glyph/content inspection.
This is not a glyph-appearance certificate: `visualAcceptance` remains unverified,
and chart labels remain outside automatic text-fit measurement. Table silhouette
measurement does not certify internal typography or glyph appearance. Review
these in the rendered page; font names and a passed size check alone are not
acceptance. On macOS inspect the actual LibreOffice font configuration; do not
assume system font installation makes a font visible to that renderer.

Native Office Math in text or tables is not reliably rendered by LibreOffice.
The reviewed `page`/`deck` publication workflow blocks such candidates with an
explicit instruction to use the LaTeX-to-PNG route. Raw `export` retains editable
Office Math for review in the intended consumer; it is not visual certification.

Actual PDF rendering also checks that each table cell's text survives extraction.
Missing/changed text blocks publication and retains `table-text-N.txt` evidence;
this detects known merged-cell import loss, but does not prove table text fits or
that every glyph looks correct. This machine's LibreOffice 26.8 reproduces a
combined row/column-span defect even for independently generated python-pptx
files. Native merge XML is preserved; no silent unmerge or content deletion is
used to force this consumer to pass.

### 批量建页 / 插页与重复提交保护

避免循环解析巨大 work JSON 再逐页 insert。先用结构化 YAML/JSON 生成页面文件和一个**有序文件路径列表**（路径相对 plan 文件）：

```json
["intro.page.yaml", "results.page.yaml", "summary.page.yaml"]
```

```bash
# 新项目：所有候选通过检查后，一次发布清单。
ansatz-slide deck import-pages ./deck --settings settings.yaml --plan pages.json --request-id initial-v1
# 已有项目：插到第 2 页之后；--after 0 插到开头，省略则追加。
ansatz-slide deck import-pages ./deck --plan additional.json --after 2 --request-id append-v1
ansatz-slide deck resume /absolute/deck/.ansatz/batches/append-v1
```

保存返回的 `resumeToken`。失败时编辑 `candidateFiles` 中保留的文件，再 resume；一批失败不发布部分页面。同一 request-id、相同原始输入只执行一次；已应用后的重复请求返回历史收据，不重复插页，也不表示当前文件仍与当时相同。相同 ID 换输入会被拒绝。默认拒绝批内或与现有页内容完全相同的页面；有意重复需在新请求中显式 `--allow-duplicates`。

修改源清单/已有源文件后，旧批次不会自动换基线：检查当前 outline，再用新 request-id 准备新批次。中断后若清单和新增文件与保存的 publication intent 完全一致，resume 会恢复收据；若处于无法判定的发布状态，会保留诊断和恢复文件并拒绝重复插入。不要删除这些记录再重试同一批次。图片资源仍相对项目根目录。

### 结构操作后的 work 恢复

每次 page work 结果包含稳定的 `resumeToken`，指向整个修订链，而非单次 revision：

```bash
ansatz-slide page resume /absolute/deck/.ansatz/work/LINEAGE
ansatz-slide page rebase /absolute/deck/.ansatz/work/LINEAGE
# 原源文件已从清单移除时，先查看当前 outline，再明确选择新的页/插入锚点。
ansatz-slide page rebase /absolute/deck/.ansatz/work/LINEAGE --page 2
```

resume 只找最新候选、检查版本，不写源文件。rebase 按源路径恢复重排后的页码；原路径消失时不猜测新页码。失败候选及其待执行 insert/edit/split 会保留；已经应用的候选则从当前源重新读取，避免恢复旧内容。rebase 本身不应用，先检查返回的候选和当前上下文，再执行返回的 page update。merge/move 的第二个锚点可能也过期，必须重开两个当前页面后重新发起。

### 表格与修复信息

`check-text` / checked preview 现在也测量表格：复制原表的文字、字体、列宽、行高和合并结构到独立的大画布，仅将单元格填充变为黑色，通过实际 LibreOffice PDF 的 144 dpi 轮廓测量检测行高扩张，包括空单元格。`measuredBounds`、`requiredHeight` 和 `overflowEdges` 给出当前消费者实测值，不套用固定“28pt 最小行高”。探针抵达画布边缘或无法提取文字时不判通过；原样 PPTX 仍需逐页视觉检查，PowerPoint/WPS 与字体外观未由此验证。

失败结果的 `repair`、`next`、`gates.hard.activeRestrictions` 是修复入口。geometry 失败仍只能调整 bounds/rotation/顺序，或保留内容拆页；文字/表格溢出按测得尺寸扩框、重排邻居或拆分内容，之后再次检查几何。不要删文字或降低质量来绕过检查，也不要用 sed 猜测 YAML 的块列表布局；用结构化解析写回，或使用 `page update --edits`。坐标与测量均是 pt，不能把页面坐标理解为屏幕像素。

### 单页插入也默认阻止重复内容

`page insert WORK --content FILE`（以及旧 session/token 入口）在渲染和发布前比较当前 deck 的页面内容；完全相同的页面会被阻止，映射字段顺序不同不构成新内容。被删除但仍保留在磁盘的页面不算当前 deck 重复，因此可以正常恢复。

有意重复时使用 `page insert WORK --content FILE --allow-duplicates`。若重复候选已被保留，可明确使用 `page update RETURNED_WORK --allow-duplicates`；该开关只适用于待插入候选，不跳过版本、几何、文字或渲染检查。旧 work 仍然不能重复提交。

列表的 text-fit 比较识别 `<ul><li>` 自动产生的项目符号和 `<ol><li>` 的段落编号，但不从正文任意删除符号/数字。字形边界仍包括这些标记，因此列表溢出仍会失败；此检查不证明编号语义或字体外观正确。
