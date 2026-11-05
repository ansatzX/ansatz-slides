---
name: ansatz-slide
description: 根据提供的材料创建和修改学术报告及课堂幻灯片。严格执行用户的论文阅读方法，组织内容、应用统一视觉风格、导出可编辑 PPTX、审阅实际页面并交付源文件。支持限定范围的修改及保留其他页的 PPTX 单页替换。
---

# ansatz-slide

**理解材料与用途 → 组织页面内容 → 按唯一 style 排版并预检源稿 → 生成 PPTX → 看实际页面并修正 → 交付。**

用户的事实、模板和明确要求优先；保留人类结论的含义、范围与确定程度，疑点明确指出。
“从头制作”须重新审视材料、提纲与页面组织；只重新导出则保留原内容。局部修改保留
非目标页面、清单与共享素材。六步直接体现在工作中，不增加六份表单或六次确认。

## 论文阅读：read.md 必须全文进入上下文

凡涉及阅读、解释、总结论文，或根据论文组织 PPT 内容，执行任务的 AI 必须先把
[reference/content/read.md](reference/content/read.md) **全文读取到当前上下文**，严格执行
其中全部要求。文件存在、读过摘要或执行过读取命令，都不能代替全文实际进入上下文。

不得为节省时间、tokens、篇幅而跳读、概括替代或删减要求，也不得自行断言摘要无损。
工具输出截断时分段读到末尾。新会话、上下文压缩或移交后，当前上下文若只有摘要，
必须重新完整读取；实际执行阅读的每个 AI 都适用。已经完整保留在当前上下文时可直接使用。

只有用户明确调整时才采用其调整，不能从“制作 PPT”推定用户同意简化阅读。
其他参考的摘要、通用建议和章节查阅规则均不能降低这项要求。

## 按任务读取：哪些文件必须读

表中的“全文”要求实际读完，出现输出截断时继续读取；“相关章节”要求在执行该操作
前读到对应说明。已完整保留在当前上下文中的同版本内容不必重复加载。

| 当前任务 | 必须读取 |
| --- | --- |
| 新建或从头制作报告 | [content.md](reference/content.md)、[style.md](reference/style.md)、[production.md](reference/production.md)、[review.md](reference/review.md) 全文；涉及论文先完整读取并执行 `read.md` |
| 修改已有源项目的内容 | `content.md`、`review.md` 全文；`production.md` 的项目、环境及导出章节；[production/cli.md](reference/production/cli.md) 的项目级修改计划章节。涉及论文阅读时先完整读取并执行 `read.md`；改布局时再全文读 `style.md` |
| 只改布局、字体或配色 | `style.md`、`review.md` 全文；`production.md` 的环境与文件边界章节；`production/cli.md` 的项目级修改计划章节 |
| 只重新导出 | `production.md` 的运行环境、渲染依赖、导出与检查章节；`review.md` 全文 |
| 替换已有 PPTX 的单页并保护其他页 | [production/replace-page.md](reference/production/replace-page.md)、`review.md` 全文；制作目标页时叠加上述内容／布局任务的必读项 |
| 只检查源文件或排查程序错误 | `production.md` 的相关操作与依赖章节；[technical.md](reference/technical.md) 的报错字段及相关共享类型。若检查视觉效果，再全文读 `style.md`、`review.md` |

新建报告还须按实际操作读取下表对应附录；制作参考中的最小示例不能代替操作说明。

| 触发条件 | 执行前必须补读 |
| --- | --- |
| 多页新建或插页 | `production/cli.md` 的“批量建页 / 插页与重复提交保护”及“结构操作后的 work 恢复” |
| 逐页 work 修改、拆分、合并、移动或恢复 | `production/cli.md` 中对应操作、限制和恢复章节 |
| 出现公式或需要制作公式图片 | [production/equations.md](reference/production/equations.md) 全文 |
| 补充模型示意图、数据图、引用或待补素材 | `content.md` 的“按讲解需要补齐页面元素”和“参考文献与外部补充”；`production.md` 的“素材准备与可替换占位” |
| 根据数据绘图，或制作数学／模型／架构示意图 | [production/figures.md](reference/production/figures.md) 的路线选择、共同规则、所选 Matplotlib／TikZ／VectorCraft 路线与检查交付；VectorCraft 命令以本机目录为准 |
| 选择 Deckcraft 创建 | `production.md` 的 Deckcraft 创建章节，以及 `production/cli.md` 的支持子集与限制 |
| 用 Deckcraft 独立查看最终 PPTX | `production.md` 的“使用 Deckcraft 独立渲染”章节 |
| 编写或修改 YAML 字段 | `technical.md` 的全局约定、清单／页面／元素基类、实际使用的元素和共享类型章节 |
| 源稿已写好，准备建页、修改或导出 | [源稿预检](reference/production/cli.md#源稿预检先于-pptx-与渲染)，先运行 `deck preflight` 并处理问题 |
| 使用形状调整参数或不熟悉的形状名称 | [technical/shapes.md](reference/technical/shapes.md) 的参数约定及目标形状行 |

## 五部分的职责

内容与阅读衔接由 `content.md` 维护；唯一视觉规范在 `style.md`；环境、源项目和操作
在 `production.md` 及其附录；实际页面验收在 `review.md`；语法与能力边界在
`technical.md` 及形状附录。`read.md` 是内容部分中用户提供的完整阅读指令，正文不得改写。

## 执行与交付

**一页事一页毕。** 在某页使用外部方法、同行结论、数据、图或公式，就在该页提供
可读的具体文献；备注、封面或末尾文献表只补充信息。讲解或推理依赖的公式须在
当页正式排版并解释符号，不能只提名称、用图中小字替代，或让听众翻到其他页查找。
正文中的数学符号、上下标和数学单位同样从 LaTeX 正式排版，不能用 Unicode 字符
或普通文本的 HTML 上下标冒充；当前受检路线插入排版后的 PNG 并保留 TeX 源。
具体要求见 `content.md` 的“参考文献与外部补充”和 `production/equations.md`。

1. **理解材料与用途。** 按必读文件确定用途与交付要求。论文先完整读取并执行
   `read.md`，再梳理问题、同行进展、方法、证据、结论与限制。
2. **组织页面内容。** 从完整阅读结果建立主线和必要前提；排版前检查每页讲什么、
   凭什么、如何衔接。通常第 2 页先讲清背景与具体研究问题，再串读各页总结句，
   检查整稿论证和相邻页推进关系；不默认结果先行或把材料切成孤立知识卡片。
   直接陈述发现与适用条件，避免
   否定、双重否定和反驳式句型堆积。大小标题之外的正文、要点和解释必须使用完整
   句子，避免关键词或换行短语的流水账；具体边界与示例见 `content.md` 的学术表达。
   不能以页面篇幅降低阅读要求。按讲解需要确定公式、引用、
   数据图与模型示意图；材料中没有现成图不等于页面不需要。主动补充有依据的素材，
   暂缺时在 `page.yaml` 中落实可替换占位及说明，不能只在提纲中提及。
3. **按唯一 style 排版。** 根据讲解关系安排图文，先保证主证据可读，再安排解释与
   标注。顶部使用“章节: 页标题”，主题凝练；概览按关系组织，少量文字不撑成三个大空框。
   需要新图时按用途采用数据绘图 package（如 Matplotlib）、TikZ 或 VectorCraft，
   将图稿和来源接入页面；具体视觉参数只在 `style.md` 维护。
4. **生成 PPTX。** 按可执行语法编写 YAML、准备项目内素材。先用 `deck preflight`
   检查正式项目或待导入的候选清单，不启动 Office；按返回页码和元素处理错误与
   待审阅提示，并核对当页引文、正式公式、符号和布局。在素材阶段检查裁图，
   从源稿就能发现的问题先解决，再生成与渲染。多页新建用
   `deck import-pages`；已有项目优先用 `deck open → 编辑返回计划 → deck revise`。
   默认 native，可选 Deckcraft 创建须先核对支持范围；同一项目不并发写入。
5. **看实际页面并修正。** `deck revise` 返回统一的 `review.viewer` 和 `review.manifest`；
   其他导出路径使用选定引擎渲染实际 PPTX。复用最终渲染，用少量可读拼图批量检查
   讲解、字体、公式、裁图和布局，疑点页才单独放大；修改后复查受影响范围。
   程序检查通过不等于视觉验收；矩阵留给代码按需诊断。
6. **交付。** 提供最终 PPTX、可复用源文件与素材，简述实际查看的范围和剩余问题。
   源文件改动后更新 PPTX；需要保护已有二进制文件的其他页时按单页替换附录执行。

## 由独立 subagent 制作并检验效果

创建或实质修订 PPTX 时，协调任务的主 Agent 将制作交给独立 subagent，后者读取
当前 skill 和所需参考，执行内容组织、页面制作、导出与初步审阅；主 Agent 检查其
实际交付，再把问题交回制作 Agent 修正。已被分派制作任务的 subagent 直接执行，
无需再递归委派同一制作任务。
这是用户指定的 skill 实效验证方式，后续制作同样执行。没有 subagent 能力时明确
说明，不能把主 Agent 自己制作宣称为独立验证。

给制作 Agent 原始任务、材料位置、输出目录和 skill 入口，使用新的上下文，不提供
主 Agent 预写的逐页答案或绕过 skill 的补丁方案。用户明确要求仍须原样传达；涉及
论文时，制作 Agent 自己全文读取 `read.md`。在隔离目录生成，保留已有交付。
交付时说明制作分工、主 Agent 发现并要求修正的问题以及实际验收范围。

常用完整导出：

```bash
ansatz-slide deck export ./deck -o ./result.pptx --offline --transition none
```
