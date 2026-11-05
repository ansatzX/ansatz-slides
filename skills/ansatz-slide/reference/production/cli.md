# 页面工作接口

模型决定内容与布局；CLI 检查输入、保护源文件版本、渲染并发布。项目级修改使用一份快照与计划；逐页 work 和旧 session/token 接口保留兼容。

## 操作阅读范围

按 [SKILL.md](../../SKILL.md#按任务读取哪些文件必须读) 的任务表选择必读文件，再读本页对应章节：

| 操作 | 必须读到的章节 |
| --- | --- |
| 候选完成、准备建页／修改／导出 | [源稿预检](#源稿预检先于-pptx-与渲染) |
| 修改已有源项目 | [项目级修改计划与统一审阅](#项目级修改计划与统一审阅推荐) |
| 多页新建或插入 | [批量建页](#批量建页--插页与重复提交保护)、[结构操作后的恢复](#结构操作后的-work-恢复) |
| 逐页修改或失败修复 | [创建与打开](#创建与打开)、[更新与修复](#更新与修复)、[几何修复](#几何失败后的布局修复与拆页)、[文字测量](#文字容纳测量) |
| 拆分、合并、移页 | [局部分页](#局部分页)、[恢复与源文件归属](#恢复与源文件归属) |
| 使用计算布局 | [局部补丁与计算布局](#局部补丁与计算布局)及当前接口的限制 |
| 使用可选 Deckcraft 创建 | [Deckcraft 支持子集](#deckcraft-创建后端) |
| 维护旧 session/token 集成 | [兼容命令](#兼容命令)及其后的对应操作 |

本附录规定操作协议，实际页面是否合格按[审阅与交付](../review.md)判断。

## 源稿预检：先于 PPTX 与渲染

先运行只读预检，修正源稿问题，再正式建页、修改或导出：

```bash
# 已有项目；可重复 --page N 限定所查页面。
ansatz-slide deck preflight ./deck --offline
# 尚未导入：settings 不含 pages，plan 沿用 import-pages 的有序候选路径列表。
# ./deck 是素材根目录，可以尚无 pptx.yaml。
ansatz-slide deck preflight ./deck --settings ./settings.yaml --plan ./pages.json --offline
# 独立 Skill 使用完全相同的核心实现。
python scripts/ansatz_slide.py deck preflight ./deck --offline
```

此命令不写清单、页面或缓存，不导出 PPTX、不启动 Office、不联网或生成占用矩阵。
输出逐页标题、可识别短引文、原生数学表达式，以及已有公式图片的相邻 `.source.tex`／`.math.txt`／`.tex`，
以及带 `page`、`element` 和 `code` 的问题，Agent 可直接检查整稿源信息。

- 确定错误：字段非法、素材缺失或为空、越界、未声明重叠等；返回非零，先修正。
  图片递归覆盖背景、元素填充、表格单元格和主题样式；问题中的 `field` 定位来源。
  共享主题素材以 `page: null` 和主题字段路径标明，`sharedAssets` 列出其引用。
- 学术提示：章节标题、可疑普通上下标、当页短引文、疑似缺公式及大框少字布局。
  `unicode-math` 提示文字框和表格单元格中的希腊字母、Unicode 数学上下标及运算符，
  包括已加 HTML 上下标的普通数学文本；按公式路线正式排版。正常非数学用法由 Agent 核对。
  `needs_review` 表示待 Agent 判断，默认不因启发式提示返回非零；`--strict` 让提示
  也返回非零。`--basic` 仅查字段、几何和素材，适合通用工具检查。
- `passed` 只表示本次可检查项通过，不证明文献准确完整、公式正确、论证成立或
  图片裁切合格。其他合法数学格式也可能得到提示，不能为消除提示硬塞无关元素。

制作 Agent 必须在首次生成前处理报告中的错误和提示，明确合理例外；不把后续
自动检查当作省略这一步的理由。批量建页、页面 work、项目计划修改与导出也在文字
测量／渲染前执行同一源稿检查；确定错误阻止后续，提示保留在 `sourcePreflight`。
这不改变旧输入语法，也不把学术排版建议变成通用 DSL 的硬性字段。

## 项目级修改计划与统一审阅（推荐）

读取目标页面并取得一份共同快照和计划文件：

```bash
ansatz-slide deck open ./deck --page 3 --page 8 --no-preview
```

省略 `--page` 读取全部页；默认批量生成所选页的预览。已有实际页面图时用
`--no-preview` 省去旧页渲染；修改仍会检查并渲染完整候选。返回页面正文、邻页上下文、
一个 `base` 和一个可直接编辑的 `plan` 路径，不需要逐页管理 work。

在返回的计划中保留 `base`，按页号与元素 ID 写修改：

```json
{
  "base": "/absolute/returned/snapshot.json",
  "pages": [
    {"page": 3, "edits": [
      {"element": "title", "changes": {"content": {"text": "修订后的标题"}}}
    ]},
    {"page": 8, "layout": [
      {"kind": "row", "items": ["figure", "explanation"], "bounds": [36, 100, 888, 320]}
    ]}
  ]
}
```

页面也可用 `content` 指向完整候选文件，或组合 `edits` 与 `layout`；路径相对计划。
空的 `edits` 保留原页。只允许修改快照选中的页，不允许重复页。

```bash
ansatz-slide deck revise ./deck --plan /absolute/returned/plan.yaml -o ./next.pptx
```

此路径对完整候选一次批量测量，调用同一核心导出一次，再渲染最终候选一次。
全部通过后才写回目标源页和输出文件；非目标源、清单及素材受版本保护。已有输出
需 `--force`。源或素材在读取后变化时拒绝套用旧计划，重新读取并核对修改。

检查失败时直接修改同一计划并重试同一命令；失败不更新正式源与已有交付。
几何失败页保留原内容，只允许调整位置、尺寸、旋转和顺序；不能删改必要内容过关。
文字失败时可查看明确标为候选版本的实际渲染。几何失败不生成候选 PPTX，审阅页显示问题。
成功后的原计划重复执行只返回同一收据，不重新修改；继续编辑用 `deck open` 开新快照。

文件写回使用保留旧版本与失败回滚，不宣称跨文件崩溃原子性。进程在写回途中被杀死时，
保留 `publication.json` 和恢复文件，阻止盲目重试，先核对现场。

返回的 `review.manifest` 和 `review.viewer` 是同一版本的统一入口：

- `review.json`：每页源文件、相对图片路径、修改标记、程序检查、问题元素与证据路径。
- `index.html`：整稿缩略图、单页大图、前后翻页，以及修改页／问题页筛选。
- 所有页的视觉状态最初都是 `not_reviewed`；程序通过不自动更新视觉结论。

打开实际图片后，记录观察：

```bash
ansatz-slide deck review /absolute/returned/review --page 3 --status needs_fix --note "纵轴标签太小"
ansatz-slide deck review /absolute/returned/review --page 8 --status reviewed --note "正文、坐标及图例完整可读"
```

`reviewed` 只记录已查看，不能替代内容正确性判断。记录绑定 PPTX 字节与源文件版本；
版本变化后不能将旧记录用于新交付。具体验收判断见[审阅与交付](../review.md)。

以下逐页 work 与旧列表式 `deck revise` 继续兼容，用于精细修改与恢复排障。

## 创建与打开

编写 `settings.yaml`，包含 `version: v2`、`size: [960, 540]`，可选 title/theme/customFonts，不填页面路径；另准备一个 `.page.yaml` 候选。

```bash
ansatz-slide deck create ./deck --settings ./settings.yaml --content ./first.page.yaml
ansatz-slide page open ./deck --page 1
```

使用新目录或只有素材、尚无清单的目录。CLI 内部保留首个候选，检查与预览成功后才发布清单和页面；失败时用返回 work 修复，不重启创建。

`page open` 返回选定页面、已记录的用途／结论／证据、相邻提纲条目、简短几何问题和预览路径，不返回其他页正文。程序仍可读取完整项目用于校验。必须用图片工具打开预览，路径本身不是图片；特定提供方的图片注入不由 CLI 负责。

## 精简输出与多页读取

`ansatz-slide --compact page open PROJECT --page 2 --page 4 --no-preview` 返回 `pages`，每页有独立 work；单个 `--page` 保留单结果格式。

`--no-preview` 只延后旧页的文字测量和渲染，标记为未验证，不跳过更新检查、源版本和素材保护。非法字段或几何仍阻止操作。多页打开是多次读取，不是多页写事务。

CLI 默认简洁输出，`--compact` 仍兼容；全局 `--full` 可展开完整工作证据，但不会生成矩阵。默认省略几何元素全集、已允许重叠和已通过文字的详细记录，读取／受阻时保留候选正文，发布成功后省去冗余正文。完整工作证据在 `revisionEvidence`；冲突时该文件属于历史修订，当前 status/issues/directives 以内联结果为准。问题元素、交集位置、文字所需尺寸、预览、限制和叙事上下文仍保留。

## 更新与修复

使用上次操作返回的确切 `work`：

```bash
ansatz-slide page update WORK --element body --changes ./fields.yaml
ansatz-slide page update WORK --content ./candidate.page.yaml
ansatz-slide --compact page update WORK --edits ./edits.json
ansatz-slide page update WORK
```

`--edits` 是非空列表，每项只能有 `element` 和 `changes`。补丁按顺序作用于同一内存候选，然后统一校验和渲染一次。无效补丁在发布前拒绝，检查失败保留合并后的候选。不能与 `--content` 或 `--element` 合用；每项仍受仅布局修复限制，原有单页发布边界内保持原子性。

最后一种形式重试保留的候选，例如渲染器恢复后。若编辑了返回的 `editable` 文件，必须通过 `--content` 传入；单纯重试只用已记录候选。不要编辑 record.json/head.json。嵌套对象合并，数组整体替换；整页内容只替换一个候选。新修订返回后（包括 blocked）旧 work 失效。外部源或素材变化需重开或明确换基线，保留旧候选。

结果为 `page-work-v1`：

| 字段 | 含义 |
| --- | --- |
| `work` | 下一次更新使用的版本绑定路径 |
| `status` | ready、applied、blocked、conflict；命令失败可返回 error |
| `applied` | 源修改是否已发布 |
| `candidates` | 保留的完整候选、可编辑路径、几何问题、预览 |
| `issues` | 候选序号、错误类型和具体原因 |
| `context` | previous/current/next 页逻辑与新鲜度标记 |
| `gates.hard` | 程序阻塞项及当前限制 |
| `gates.live` | 模型负责的语义要求和可选建议，CLI 不评判 |
| `next` | 下一条命令与允许输入 |

`ready` 表示读取、未发布；`blocked` 保留候选。另查 `applied`，写入后的预览或上下文组装失败不能被误读为没有改源。`conflict` 拒绝过期引用。`error` 在发布状态未知时可返回 `applied: null`，重试前检查当前源文件。几何成功不等于视觉或科学验收。

## 几何失败后的布局修复与拆页

几何失败后 `layoutOnly` 为 true，只能修改 bounds、rotation 和元素顺序；内容、字体样式、图片来源、元素集合及重叠豁免被冻结。非布局修改被拒绝时保留原候选和 work，不增加几何失败计数，可用相同 work 提交布局修正。

`geometryFailures` 按 work 链记录每个候选的连续几何失败次数，含首次检查。几何通过即清零，即使随后渲染失败。第三次起 guidance 建议考虑拆页，不自动改内容，也不强制拆页。

受阻单页可执行 `page split`，包括尚未产生正式清单时。须重新分配全部原元素，不能删、重复或改内容与样式，并保留备注。新页通过后恢复普通内容编辑。结构操作若被另一源页阻挡，`blockingPages` 返回对应几何问题，供打开和修复。

## 默认几何检查与按需矩阵

普通 open/update/import/export 直接检查矩形边界，不分配占用网格，不输出 RLE 或灰度图。失败反馈保留元素 ID、交集与越界位置，完整几何报告写入工作目录。矩阵仅用于下述显式诊断，由代码消费；不要把完整矩阵读入 LLM 上下文，也不要用灰度占用图代替实际页面视觉验收。

正面积边界重叠需在页面中逐对声明 `allowedOverlaps` 和非空理由，越界元素被阻止。声明只用于有意叠层，不批量豁免碰撞。旋转采用保守矩形包络，不测文字墨迹／溢出、阴影和透明度。分数边界仅共用栅格不算几何相交；非法或缺失几何保留候选与错误，不伪造有效矩阵。

### 独立几何诊断

```bash
ansatz-slide page check-overlap --project ./deck --page 2 --output ./work/geometry-2
```

输出目录必须是新的。不需要 Office，生成 report.json、occupancy.tsv.gz（0/1）、counts.tsv.gz、occupancy.png 和 overlap.png。矩阵按 `[y][x]` 索引，原点左上。`--cell-size` 可改诊断分辨率，显式矩阵仍拒绝超过四百万格；普通几何检查不受网格大小限制。

有意重叠写入候选：

```yaml
allowedOverlaps:
  - elements: [frame, label]
    reason: The label sits inside its background frame.
```

ID 须存在且不同，不接受重复配对、通配符或空理由。声明不允许越界或其他碰撞。零面积线条允许，其他零面积元素无效；全画布填色宜用页面背景。

## 文字容纳测量

几何通过后，预览使用 LibreOffice/Poppler 测量原生横排文字。探针保留框宽、字体字号、富文本样式、换行、段间距和行距，扩大高度以暴露原框可能截断的文字，再以 PDF 坐标测量占用范围，不按字符数估算。

`textFit` 返回元素 ID、请求样式、PDF 实际字体、测得边界、所需宽高及溢出／未验证原因。`renderedFonts` 可显示字体替换，本机结果不保证其他字体或 Office 软件一致。

溢出或无法测量会阻止发布并保留 work，修正候选后重试。单纯文字失败不冻结字体字段，但先前几何失败仍有自己的限制。

```bash
ansatz-slide page check-text --project ./deck --page 2 --output ./work/text-2
```

使用新输出目录，保留探针 PPTX/PDF、边界数据和 text-fit.json，失败返回非零。work 携带测量结果，deck export 在替换输出前测量即将序列化的同一份内存文字。缺少 LibreOffice、pdftotext 或 pdffonts 是阻碍，不能判通过；不会自动缩字或删内容。

横排原生文字与输出富文本在范围内；竖排和原生 Office Math 未验证并阻止此流程。表格另测软件渲染轮廓及扩张，图表标签不测，图片内文字不属于原生文字。所有对象仍须视觉检查，探针触及上限时标未验证。单词范围不证明字形和可读性。validate、旧 export 和底层 Python writer 保留各自字段／几何检查契约，文字门槛使用 deck export。

### 页面 Agent 的候选交回检查

页面负责人在交回前运行本页检查并修复，主 Agent 的整稿检查是复核。并行制作时，
每页使用自己的候选目录；本页测量不需要更新共享正式项目，也不需要渲染整稿。

尚未导入的页面，在其专属目录建立单页检查清单，例如 `check.pptx.yaml`。采用正式
项目相同的 `size`、`theme` 和 `customFonts`（如有），`pages` 只引用本页候选文件：

```yaml
version: v2
size: [960, 540]
pages: [candidate.page.yaml]
```

这个例子没有主题；实际项目有主题时须一并带入，不能用不同外观测量。把本页引用
的本地素材复制到候选目录内，保持相同相对路径，包含主题引用的素材；不要改共享
原件，也不要以指向项目外的符号链接绕过素材边界。新素材同样以交回版本参与检查。
已导入的页面可使用自己的工作副本和受检页面操作，但不能由多个负责人写同一正式项目。

```bash
ansatz-slide deck preflight ./page-task/check.pptx.yaml --offline
ansatz-slide page check-text --project ./page-task/check.pptx.yaml --page 1 --output ./page-task/checks/text-v1
```

先处理字段、素材和几何问题，再测文字。`deck preflight` 不测文字；YAML 解析、
画布内边界及无重叠均不能代替第二条命令。该单页检查项目中的页码固定为1，
回传时注明它对应整稿哪一页。检查清单属于专属工作目录，不合入正式页序。

修订后采用新输出目录重跑受影响检查，并回传命令、当前候选和素材、预检报告、
`text-fit.json` 路径及结果。已发现的可测文字溢出应在本页修复；工具缺失或运行
失败时回报受阻。原生公式及混排文本返回 `unverified` 时保留未验证状态，核对
报告中其余普通文字；不能把整个非零退出码解释为“只有公式问题”而忽略同时存在的
溢出。只有这些未验内容尚待处理时，可交回明确标注范围的候选，不宣称整页通过。
公式保留与目标软件检查要求见[公式附录](equations.md)。

## 局部分页

```bash
ansatz-slide page insert WORK --content ./new.page.yaml --position after
ansatz-slide page split WORK --content ./a.page.yaml --content ./b.page.yaml
ansatz-slide page merge WORK --next ADJACENT_WORK --content ./combined.page.yaml
ansatz-slide page move WORK --anchor OTHER_WORK --position before
ansatz-slide page remove WORK
```

merge/move 先打开另一页。存在待处理候选时先修复或重开，再执行结构操作；几何受阻单页的保内容拆页例外。受阻 insert/split/merge 保留全部操作候选，例如修复第二个候选：

```bash
ansatz-slide page update WORK --candidate 2 --element body --changes ./fields.yaml
```

修复后重试同一结构操作。成功返回可继续编辑的主页面 work；其余页与证据在适用时保留于 `operationCandidates`。源文件名标识页面，清单顺序决定页码。退役或删除的源文件保留磁盘上，写清单前所有结果页须通过几何检查。

## 模型编写的提纲

```bash
ansatz-slide deck outline ./deck
ansatz-slide deck outline ./deck --page 1 --content ./intent.yaml
```

意图接受 purpose、claim、previousConnection、nextConnection 字符串，以及 evidence 来源说明列表；也兼容旧 connection 字符串。requirements 和 suggestions 是独立非空文本列表。更新替换整页意图，须提交想保留的全部字段。模型负责书写，CLI 不从标题推断论证。

提纲绑定源路径，移动后保留。页面、引用本地素材、画布／主题／自定义字体或相邻身份及依赖变化后标 `needsReview`；插入／拆分／合并的新源在模型补充前无已确认意图。退役条目保留于退役列表，更新一页不动无关条目，语义一致性仍由模型判断。

## 程序限制与语义要求

每个 work 响应区分以下职责：

- `gates.hard`：程序检查源版本／范围、字段／素材、几何、仅布局修复和渲染。blockingIssues 给出拒绝原因，activeRestrictions 描述候选冻结，applied 表示发布而非语义质量。
- `gates.live.requirements`：模型必须遵守的语义要求，附页面角色、来源、新鲜度；不执行为程序条件，也不自动标已满足。
- `gates.live.suggestions`：可选建议，含三次失败后的拆页建议，模型可选择另一种合法布局。

例如用 `deck outline PROJECT --page N --content FILE` 保存：

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

context.previous/current/next 各自通过 intent 提供用途、结论、证据和衔接，只展开当前页正文。不存在的相邻页和缺失意图为 null，不从标题代填。relationNeedsReview 标记相邻变化，也包括没有相邻快照的旧意图。新鲜度是复核提示，不是硬门槛；CLI 无法评判不意味着语义要求可忽略，几何或导出成功不代表已满足。

## 导出

```bash
ansatz-slide deck export ./deck -o ./result.pptx --offline
ansatz-slide inspect ./result.pptx
```

deck export 默认无切页动画，总会重查当前源文件；--force 只授权替换输出，不绕过几何。逐页修改不覆盖整稿 PPTX，须查看最终导出。

旧 export、page check/edit/patch session/token、deck check 与草稿清单创建见[兼容命令](cli.md#兼容命令)。新流程统一使用 work。page check-overlap 是独立只读诊断，不是额外必做步骤。

## 恢复与源文件归属

work 在 `.ansatz/work`，提纲在 `.ansatz/outline.json`；它们是本地状态，清单和页面仍是输入。保留的 work／备份不自动删除，结构发布失败可能留下未引用新页面，清理前检查恢复记录。

外部写入和进程崩溃不是数据库事务，中断后重开源文件、查看候选和恢复文件，不能认为进程失败就没有写入。锁由操作系统持有，进程退出（含异常）即释放；持久 `.lock` 文件是协调用 inode，不证明仍有活跃持有者，也不要删除。锁正被持有时立即返回可重试冲突。切换锁协议前结束旧版 CLI。

发布在写前写后重查预览依赖的本地素材哈希，变化则拒绝并保留恢复文件，不接受未预览的新图片。创建及重试检查所有保留清单名 pptx.yaml 和 *.pptx.yaml。没有依赖 token 的旧提纲需先复核一次，此后跟踪页面、素材和外观依赖。

正式清单／页面首行提醒用 ansatz-slide 修改；候选和 JSON 状态无此行。它不是文件权限限制。含注释的源文件用 YAML 解析器。未修改导入文件保持原状，下一次 CLI 写入才增加提醒。

## 整稿意图与有来源的要求

用 `deck brief PROJECT --content brief.yaml` 保存模型编写的整稿论证，页面上下文中位于 context.narrative.brief，另有已有的前后页逻辑。`deck brief PROJECT` 读取当前状态。

```yaml
purpose: Explain when the result holds
audience: Research group
centralClaim: The improvement depends on the stated experimental conditions
sections:
  - id: evidence
    claim: Establish the result and its limitations
    sources: [1.page.yaml]
```

使用真实源文件名，各章节合计覆盖所有当前页面，一章可含多页。brief 保持简短便于局部编辑，它不是经过认证的用户意图摘要。

CLI 跟踪源／素材依赖和清单顺序。源变化触发相关章节复核，插入、拆合、删除和重排触发结构复核。章节论证变化标记其页面意图，目的／受众／中心结论变化影响全部页面意图。复核后重写完全相同 brief 不使其他当前意图失效，新鲜度不证明连贯性。

用 `deck directive PROJECT --content directive.yaml` 记录有来源的要求或建议：

```yaml
id: preserve-limitations
kind: user_requirement
text: Preserve the stated limitations
source:
  reference: path-or-message-reference-to-the-actual-instruction
  quote: Preserve the stated limitations
scope: [1.page.yaml]
```

示例 reference/quote 必须替换成用户实际提供的证据。kind 为 user_requirement 或 model_proposal，scope 为 deck 或非空当前源文件名列表。模型建议引用自己的计划或理由。CLI 只记录调用方提供的归属，无法认证人类或证明引用支持转述。不能把推测偏好标成明确用户要求，旧 outline requirements 仍标为模型建议。

同 ID 写入修订文字／证据／范围并保留旧版，不可改变来源种类。明确撤销：

```bash
ansatz-slide deck directive ./deck --revoke preserve-limitations --source actual-instruction-reference --quote 'Actual revocation wording'
ansatz-slide deck directive ./deck --history
```

撤销项退出当前要求，来源与前后历史仍在 `.ansatz/narrative.json`。不能因布局困难撤销用户要求。源变化只请求复核，不撤销；范围内源被拆合或删除后，活跃要求留在 unresolvedDirectives，直到明确调整范围或凭证据撤销。页码移动不改变基于源路径的范围。

gates.live.userRequirements 和 modelProposals 区分明确要求与可修改计划；gates.facts 指明程序测量字段及候选／work 状态，不证明语义验收。兼容 requirements 字段保留来源标记，不引入新的程序发布门槛。

交付需保留创作上下文时携带 narrative.json 和 outline.json。`--history` 按需读历史，默认读活跃记录。本功能不压缩响应，也不改变候选和文字载荷格式。

## 一次命令完成多页修改与交付

打开目标页后写 JSON/YAML 计划，相对路径以计划文件为基准：

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

只接受本项目已有页面的 edit work，每页只能出现一次。首次写源前检查全部 work 和补丁语法，再按普通更新执行候选，包括仅布局限制、文字测量、预览和版本保护。后续失败停止计划，保留先前已写页面及其 work，已有输出 PPTX 不变。appliedPages 与 exported 分别说明源写入和交付结果，这是顺序编排，不是整稿原子事务。

完整候选离线、无切页动画导出，经结构检查和 LibreOffice/Poppler 渲染后发布；暂存 `.ansatz/deliveries/`，覆盖输出需 --force。交付期间源变化阻止最终发布。返回 preview.changedPageImages、全部页图、timings 和持久 report，预览来自实际输出字节，直接打开它们，不重复导出／检查／渲染。

渲染失败后可把未变化源页连同最新 work 和原内容加入计划，重试交付。保留的源、work 与暂存可用于恢复；字体和 PowerPoint/WPS 原生效果仍需另查。

文字测量同时保留原高度框的中／底对齐探针与扩高顶对齐探针。扩高探针的负 top 不单独证明居中框溢出。不要靠空行补偿测量原点，应使用实际框边界并保留预期对齐。

## 局部补丁与计算布局

下一版本优先保留已有页，不重新序列化整页。计划可将 edits（先执行）与 layout 放在一次检查中：

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

使用 `ansatz-slide --compact deck revise PROJECT --plan plan.json -o next.pptx`。
单页 `page update WORK --layout layout.json` 接受操作列表，可与 --edits 合用，不能与整页 --content 或单元素 --element 合用。

- row/column：items 为 ID 或 ID 组，只平移，不改变大小、组内偏移、层级、文字和样式。bounds 是可用区域，未给 gap 则均分剩余空间；非负 gap 则从区域起点排列。横向对齐 align 为 start、center（默认）、end。组放不下则失败，不默默缩放或缩字。
- segments：单个形状 ID，每个有正有限 weights。沿 axis（默认 x，可为 y）按比例分配，gap 非负、默认零。只改 bounds；标签是独立元素，须明确安排，不从权重猜文字或数据。
- 引用 ID 须存在且每操作不重复，旋转元素需明确修改 bounds。未知参数、非有限数、空间不足、非法权重均在发布前拒绝。操作顺序作用于副本，不动未引用元素与页元数据，几何／文字和已有冻结限制仍生效。

局部迭代只需打开目标页、写小计划、执行交付、看变更页图，再返回 PPTX。改措辞或间距不重写 brief、源页或新布局脚本，结构重设计才可能需要整页内容。

预检保护每个候选新增的本地图片以及原源文件／素材／计划，不能把它们用作交付路径。更新、导出、最终渲染时有内容变化则阻止交付，appliedPages 已列出的源修改仍然有效。

### 渲染失败与证据边界

执行／渲染失败后查看 issues[].diagnostic 中的本地堆栈，用返回 work 和 `page update <returned-work> --content FILE` 修复。失败插入保留插入操作。进入候选处理的操作取代旧引用，早期拒绝可能保留原引用。源冲突用下方 resume/rebase；只有明确放弃候选或重建 merge/move 双锚点时才重新打开。

文字测量同时检查提取文字与源内容一致性及占用边界。不一致阻止发布，应检查字体、字形和内容。visualAcceptance 仍为未验证；图表标签不自动测量，表格轮廓也不证明内部排版和字形，须看实际页面。macOS 上要检查 LibreOffice 实际字体配置，系统安装并不保证渲染器能看到。

LibreOffice 不能可靠渲染文字／表格里的原生 Office Math，受检 page/deck 流程仍阻止此类候选；按[公式说明](equations.md)用原始 export 制作原生数学候选并在可用目标软件中检查，不能为绕过测量而转成图片。

PDF 渲染还核对每个表格单元格文字能否被提取；缺失或变更阻止发布并保留 table-text-N.txt。它能发现已知合并单元格导入丢字，但不证明容纳或字形。曾在 LibreOffice 26.8 对独立 python-pptx 文件也复现行列混合合并问题。保持原生合并 XML，不通过默默取消合并或删内容让该软件通过。

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

批量建页先逐页检查几何，再合并文字探针并分批渲染候选页；不会逐页启动完整渲染链。
任一候选失败仍保留整批候选，不发布部分页面；文字或几何失败会标明对应候选。
整稿导出也合并文字测量，仍检查当前内容，不复用跨命令的历史测量结果。

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

## Deckcraft 创建后端

使用方式见[制作参考](../production.md#可选创建后端deckcraft)。以下限制仅针对 `--backend deckcraft`；默认 native 的字段范围见[技术参考](../technical.md)。

首版支持范围：

- 普通文本及换行、单一 `fontFamily` 字符串、字号、颜色、粗体、斜体、对齐、换行开关和纯色背景。
- `rect`、`roundRect`、`ellipse`、`triangle`、`rightArrow` 形状，纯色填充、实线边框及形状旋转。
- PNG/JPEG 图片，显式 `fit: {mode: contain}`；画布尺寸、纯色页背景、备注和 none/fade 切页。
- 元素 ID 映射为形状名称；元素顺序保持图层顺序。颜色须显式使用 `#RRGGBB`。

富文本/HTML、分语言字体对象、主题样式、表格/图表、原生公式、元素动画、裁剪、
渐变及其他未列出的字段会明确报错，保留已有输出，不静默降级或自动改用 native。
遇到不支持字段，保留用户内容并改用默认后端，或在授权范围内调整源文件。

此选择目前只接入 `deck export` 和基础 `export`；`page` 预览、`deck import-pages`、
`deck revise` 与二进制单页替换仍沿用原实现。编辑仍走 YAML/page 工作流，再显式
用所选后端导出；直接在 Deckcraft 改 PPTX 不会反向更新 YAML。

## 兼容命令

新创作使用 work；旧集成接口保留，需显式 session/token，不实现 work 链布局冻结和三次失败建议。共享字段、几何和源发布检查仍生效。

## 旧接口：检查与修改页面

```bash
ansatz-slide page check --project ./deck --page 2 --session ./work/page-2
ansatz-slide page edit ./work/page-2 --token TOKEN --content ./candidate.page.yaml
ansatz-slide page patch ./work/page-2 --token TOKEN --element body --changes ./fields.yaml
```

TOKEN 是最新返回值，不是字面量。session 固定一页，提供 editablePage、pageSource、几何和预览。page edit 不带 --content 时读会话草稿；元素补丁递归合并对象、整体替换数组并保留省略字段，不能改变元素身份／类型。

成功后用新 token；待处理草稿不能被再次 check/patch 默默丢弃，须明确复用或另选 session。源、全局设置或相关素材变化使旧 token 失效，影响多个位置的源别名会被拒绝。

几何受阻保留草稿与诊断，不返回 Office 图片/PPTX，退出非零。edit/patch 成功只更新单页源和预览，不更新整稿。遵循本文件的几何与恢复规则。

## 旧接口：结构修改

以下示例都需要新检查的 session 及真实 token：

```bash
ansatz-slide page insert ./work/page-2 --token TOKEN --content ./new.page.yaml --position after
ansatz-slide page split ./work/page-2 --token TOKEN --content ./a.page.yaml --content ./b.page.yaml
ansatz-slide page merge ./work/page-2 --token TOKEN --next-session ./work/page-3 --next-token NEXT_TOKEN --content ./combined.page.yaml
ansatz-slide page move ./work/page-2 --token TOKEN --anchor-session ./work/destination --anchor-token ANCHOR_TOKEN --position before
ansatz-slide page remove ./work/page-2 --token TOKEN
```

merge 需要紧接的下一页；move 使用已检查锚点身份。结构修改校验结果页集、保留退役源并使旧清单 token 失效，使用返回的下一条命令。不能删除最后一页，源分页后须导出整稿。

## 旧接口：草稿清单与提纲摘要

```bash
ansatz-slide deck create --draft ./deck/deck.draft.yaml --output ./deck/pptx.yaml
ansatz-slide deck check --project ./deck
```

草稿创建接受显式页面路径，所有页须通过几何，目录不能有正式清单。草稿与输出同目录，输出必须新建且命名 pptx.yaml 或 *.pptx.yaml。此接口不执行新 work 创建预览，新流程使用 `deck create PROJECT --settings FILE --content FILE`。

deck check 只读有序标题／来源摘要，不是语义审阅或可编辑整稿载荷；模型意图用 deck outline。

## 旧接口：导出

`export PROJECT -o FILE` 保留且默认 fade，deck export 默认 none。二者均接受 --transition、--offline 和 --force。二进制替换见[单页操作](replace-page.md)。

会话与 work 共用内核锁，进程退出释放，持久锁文件不要手工删除。恢复及文件系统限制见本文件。不要修改会话状态或通过批量写源绕过局部失败。
