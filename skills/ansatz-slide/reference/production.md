# 制作与修改

本部分负责源项目、环境、生成和修改操作。内容取舍见[内容组织](content.md)，视觉参数见[唯一风格](style.md)，最终检查见[审阅与交付](review.md)。

## 按任务选择操作

- 源稿准备好后先运行 `deck preflight`：支持正式项目和待导入候选，见[源稿预检](production/cli.md#源稿预检先于-pptx-与渲染)；不需要 Office 或 PPTX 输出。
- 首次试作：使用下方最小示例。
- 多页创建与修改：见 [CLI 操作](production/cli.md)，多页新报告使用 `deck import-pages`；已有项目优先使用 `deck open` 返回的一份计划，经 `deck revise` 批量修改并打开统一审阅入口。
- 公式素材：见[公式制作](production/equations.md)。受检流程默认使用 LaTeX 生成 PNG 并保留源文件。
- 数据图、数学与模型示意图：见[绘图制作](production/figures.md)，按用途选择 Matplotlib、TikZ 或 VectorCraft。
- 保留已有 PPTX 其他页面：见[二进制单页替换](production/replace-page.md)。

## 运行环境

需要 Python 3.11+ 和锁定的 PyYAML 6.0.3。纯 JSON 输入可以不依赖 PyYAML，但 CLI
生成的正式 YAML 含注释，应使用正常安装环境。

### 按操作准备依赖

| 操作 | 所需工具 |
| --- | --- |
| 源稿预检 `deck preflight` | Python 3.11+；YAML 使用 PyYAML，无 Office／Poppler 依赖 |
| 读写 YAML、校验、基础 native 导出与结构检查 | Python 3.11+、PyYAML |
| 受检建页、修改、`deck export` 的文字测量与自动预览 | 上述环境 + LibreOffice + Poppler |
| 可选 Deckcraft 创建 | 上述导出流程 + `deckcraft-cli` |
| 独立查看最终 PPTX | Deckcraft、LibreOffice、Microsoft Office 三选一 |
| LaTeX 生成公式图片 | `pdflatex` 与所需宏包 + Poppler 的 `pdftocairo`，见[公式制作](production/equations.md) |
| 根据数据绘图 | 绘图用 Python 环境及 Matplotlib 等所选 package，见[绘图制作](production/figures.md#matplotlib依据数据作图) |
| TikZ 示意图 | TeX 引擎、TikZ 及所用宏包 + Poppler；中文和 `fontspec` 示例使用 XeLaTeX |
| VectorCraft 示意图 | `vectorcraft-cli` 可批量生成和导出；`vectorcraft` 窗口可查看与手工编辑原生图稿，Agent 控制画布时使用控制通道 |

`uv` 用于管理项目环境，不是导出引擎。参考 PPTX 是方法与风格依据，不是运行依赖。
三条绘图路线按需准备，不是基础 PPTX 导出的必装依赖；依赖只安装到项目环境。
创建后端决定怎样写 PPTX，文字测量用于提前发现容纳问题，视觉引擎用于看实际输出；
三者不能互相代替。选择 Deckcraft 创建或验收，并不移除当前受检流程中的 LibreOffice/Poppler。

## 从仓库运行

```bash
mkdir -p tmp/uv-cache tmp/test-tmp
export UV_CACHE_DIR="$PWD/tmp/uv-cache"
export TMPDIR="$PWD/tmp/test-tmp"
uv sync --frozen
uv run --frozen ansatz-slide --help
```

依赖已安装时，也可使用 `PYTHONPATH=src python3 -m ansatz_slide`。
字段示例见[最小示例](#最小示例)，创作命令见[CLI 操作](production/cli.md)。

## 独立 Skill

从仓库安装到一个 Skill 父目录：

```bash
uv run --frozen ansatz-slide install-skill --target ./tmp/skills
```

生成目录包含指令、`python/ansatz_slide`、模板、脚本和锁定的环境配置。在安装
目录中运行：

```bash
mkdir -p tmp/uv-cache
UV_CACHE_DIR="$PWD/tmp/uv-cache" uv sync --frozen
uv run --frozen python scripts/ansatz_slide.py --help
```

将目标替换为实际 Skill 父目录。覆盖已有安装需在用户授权范围内使用 `--force`。
安装复制当前包，后续仓库修改不会自动更新已安装 Skill。升级前结束旧 CLI 写入
进程，尤其在锁协议变化时。

## 渲染依赖

实际 PPTX 的视觉验收从 Deckcraft、LibreOffice、Microsoft Office 中选一个，见
[审阅规定](review.md#渲染引擎)。以下是当前 CLI 内置流程的依赖，不代表三引擎均已接入。

页面创建、打开和更新的预览使用 PATH 中的 LibreOffice（`soffice` 或 `libreoffice`）
及 Poppler（`pdftoppm`、`pdftotext`、`pdffonts`）。**Poppler 是 ansatz-slides 的系统依赖**，
不是 Python 包；公式图片另使用其中的 `pdftocairo`。CLI 与 pip/uv 不安装这些系统工具。工具缺失或
渲染失败时保留候选并阻止发布；环境恢复后重试原计划或返回的 work。`deck open --width` 与 `page open --width`
设置预览分辨率。

`validate`、旧 `export`、`inspect` 和 `page check-overlap` 不依赖 Office 渲染。
`deck export` 与页面预览需要 Office 测量原生文字。导出成功不等于视觉检查通过。
公式图片另有[排版依赖](production/equations.md)。

## 可选创建后端：Deckcraft

YAML DSL 仍是唯一内容源。默认 `--backend native` 使用本项目 OOXML 导出器；明确
选择 `--backend deckcraft` 时，将同一 DSL 映射为 Deckcraft JSON 命令，从空白文稿
创建原生文字、形状与图片，再导出 PPTX。无需维护另一份 Deckcraft 源文件。

```bash
ansatz-slide deck export ./deck -o ./result.pptx --offline --transition none --backend deckcraft
deckcraft-cli render ./result.pptx --all --scale 2 ./tmp/deckcraft-preview
```

需要 PATH 中的 `deckcraft-cli`，已在 0.10.0 验证。属于可选依赖，不由 pip/uv 安装。
`deck export` 仍以 LibreOffice/Poppler 测量 DSL 文字；它不是 Deckcraft 实际排版的
容纳保证。最终须检查 Deckcraft 渲染图，字体、换行和行距可能与原导出器不同。

支持子集与编辑限制见 [Deckcraft 创建后端](production/cli.md#deckcraft-创建后端)。
先查支持范围再选择，不为使用可选后端而丢弃内容或降低排版要求。
导出器会先检查后端支持的源字段，再解析素材并检查实际图片格式；这些检查均在
Office 文字测量前执行，不支持的输入提前拒绝并保留已有交付。

## 使用 Deckcraft 独立渲染

Deckcraft 0.10.0 的本机 CLI 支持无窗口读取和渲染实际 PPTX；无需启动 GUI 或 MCP。
先用 `deckcraft-cli --version`、`deckcraft-cli render --help` 确认安装版本的接口。

```bash
# 全稿 PNG；960 × 540 画布在 scale=2 时输出 1920 × 1080。
deckcraft-cli render ./result.pptx --all --scale 2 ./tmp/deckcraft-preview
# 页索引从 0 开始，以下渲染第 3 页。
deckcraft-cli render ./result.pptx --slide 2 ./tmp/page-3.png
deckcraft-cli info ./result.pptx
deckcraft-cli convert ./result.pptx ./tmp/result.pdf
```

全稿图片名为 `slide-01.png`、`slide-02.png` 等。渲染后打开实际图片检查，不能用
命令成功代替验收。GUI 查看使用 `deckcraft ./result.pptx`，播放可加 `--show`。

以上渲染命令独立于创建后端；当前 ansatz-slide 自动预览和文字测量仍调用 LibreOffice/Poppler。
Deckcraft 能直接出 PNG，不代表已经替换文字容纳检查，Poppler 仍保留为系统依赖。
不同引擎可能产生不同换行和行距；记录本次视觉验收使用的引擎，不自动重存原始 PPTX。

## 导出与检查

```bash
ansatz-slide validate ./deck
ansatz-slide deck export ./deck -o ./result.pptx --offline --transition none
ansatz-slide inspect ./result.pptx
```

使用真实路径。`deck export` 默认无切页动画，旧 `export` 和 `replace-page` 默认
fade；`--transition` 控制切页而非元素动画。字体不嵌入。

已有输出须使用 `--force`，它只允许替换输出，不跳过字段和几何检查，也不允许
覆盖源文件或素材。`--offline` 拒绝远程图片，否则导出可读取明确引用的 HTTP(S)
素材。页面预览只接受本地或 data URL 素材，本地路径必须在项目内。

保留已有 PPTX 的其他页面时用[单页替换](production/replace-page.md)。最终遵循[审阅与交付](review.md#交付)。
旧 session/token 接口见[兼容命令](production/cli.md#兼容命令)。

## 字体显示问题

文字提取成功或 `pdffonts` 列出字体，不证明中文字形实际可见。检查 PNG/PDF，
在声明成功前确认没有方框、缺字或意外替换。

CLI 使用独立转换配置，不能假设其字体与另一 GUI 配置相同。先检查真实字体
配置与所用配置目录，Skill 不自动复制字体或更改系统设置。字体显示失败仍是
交付缺陷。

## 项目文件

```text
project/
  pptx.yaml                  # CLI-managed settings and ordered page paths
  page-<id>.page.yaml         # CLI-created page sources
  media/                     # supplied or prepared local assets
  .ansatz/                   # work revisions and model-authored outline
  .ansatz-recovery/           # retained publication recovery, when needed
```

导入的项目可以采用 `pages/01.page.yaml` 等相对路径，页码只由清单顺序决定。
所有素材引用都相对清单所在目录，包括页面文件内的引用。交付时携带源文件和
素材；运行状态与恢复文件不是编译输入。

清单命名为 `pptx.yaml` 或 `*.pptx.yaml`，使用 `version: v2`，页面以 `.page.yaml`
结尾。目录输入只在根目录查找唯一清单。多清单目录可明确指定清单文件，但新建
项目拒绝再添加第二份清单。独立页面缺少画布和主题上下文。

## 表达与文件边界

YAML/JSON 编码正式数据，富文本使用支持的 HTML 子集，公式使用[公式路线](production/equations.md)。
TypeScript 类型与风格 Markdown 都是说明，不是可执行页面。按字段查[格式参考](technical.md)。

本地图片必须位于项目内。只改一页图片时先复制共享素材。缺少证据应明确占位，
不编造内容。目标查看器须有可用字体。

`page update` 生成局部预览，不自动更新已有完整 PPTX；`deck revise` 会生成并渲染完整输出。单独修改源文件后需重新导出。要求
保留现有文件非目标页时使用[二进制单页替换](production/replace-page.md)。最终文件要独立于
源页面预览接受检查。

## 素材准备与可替换占位

按[内容需求](content.md#按讲解需要补齐页面元素)主动准备必要图示。可从用户材料、
经核实的网络来源或对应代码取得素材，也可使用适当的绘图与图片工具生成；不限定
为从论文裁图。数据图保留输入数据和绘制脚本，模型图保留来源、版本与简化说明。
新图按[绘图制作](production/figures.md)选用 Matplotlib 等数据绘图 package、TikZ 或
VectorCraft；三条路线共用需求判断、来源核对、项目内素材和最终 PPTX 验收。

暂缺素材时，使用已有 DSL 的形状与文字创建可替换占位，不能引用不存在的图片让
导出失败，也不新增未经实现的 `placeholder` 等字段。给元素稳定而明确的 ID，如
`unimol-diagram-slot`、`unimol-diagram-label`；设置最终图需要的 `bounds`，保持适合
其内容的比例。若文字位于框内，按现有语法声明有意重叠。

框内简要写清“待补图：具体对象与用途”，让读者知道它尚未完成；在该页 `notes`
中记录应展示的对象与关系、必要标签或坐标及单位、来源／数据位置、当前已知结论
与待核事项。例如，模型占位说明输入、距离信息、编码及预测输出；数据占位说明
比较哪几组、横纵轴、数据支持什么，或正在检验什么问题。不强制统一图型或固定框数。

替换时沿用约定的元素 ID 与区域，改为受支持的 `image` 或图表元素，删除占位文字
及失效的重叠声明，并补齐真实素材、来源与图注。保留原素材比例和必要坐标；替换后
重新导出并检查受影响页。占位允许人类或其他 LLM 后续接手，但不能被记录成图已完成、
数据已验证或内容已最终验收。

## 最小示例

先使用文字、图片素材、矩形和线条。原生图表与表格属于兼容能力，通常使用
外部工具或用户素材制作图表。以下两个输入通过实际导出器进行回归检查。

本例只创建一页。多页已准备好时，使用 `deck import-pages` 和有序路径列表，
详见[CLI 操作](production/cli.md)，不要为每页重复单页创建流程。

将第一段保存为 `settings.yaml`，第二段保存为 `first.page.yaml`，运行：
`ansatz-slide deck create ./deck --settings ./settings.yaml --content ./first.page.yaml`。
CLI 管理页面文件名和正式清单。失败时保留候选，按返回 work 执行 `page update`；
成功时返回首个预览。素材须放在 `./deck` 项目内。

## `settings.yaml`

```yaml
version: v2
title: 学术报告示例
size: [960, 540]
```

## `first.page.yaml`

```yaml
pageType: content
allowedOverlaps:
  - elements: [title-bar, title]
    reason: 页标题位于顶部标题条内。
  - elements: [evidence-frame, missing-evidence]
    reason: The evidence placeholder label belongs inside its background frame.
background: {type: solid, color: "#FFFFFF"}
elements:
  - elementId: title-bar
    elementType: shape
    bounds: [0, 0, 960, 48]
    shapeName: rect
    fill: {type: solid, color: "#BD2333"}
  - elementId: title
    elementType: text
    bounds: [28, 4, 904, 40]
    content:
      fontFamily: {latin: Arial, ea: Microsoft YaHei}
      fontSize: 24
      color: "#FFFFFF"
      bold: true
      text: "导读: 问题与材料"
  - elementId: evidence-frame
    elementType: shape
    bounds: [48, 140, 540, 300]
    shapeName: rect
    fill: {type: solid, color: "#F2F2F2"}
  - elementId: missing-evidence
    elementType: text
    bounds: [72, 245, 492, 72]
    content:
      fontFamily: {latin: Arial, ea: Microsoft YaHei}
      fontSize: 22
      color: "#202020"
      text: "待补充用户素材，非实验结果"
  - elementId: interpretation
    elementType: text
    bounds: [628, 160, 284, 210]
    content:
      fontFamily: {latin: Arial, ea: Microsoft YaHei}
      fontSize: 22
      color: "#202020"
      text: "用材料支持的解释替换这里的说明。"
```

本例采用唯一风格的顶部标题条与配色，中文使用微软雅黑，英文与数字使用 Arial。运行前确认这些字体
可用，或替换为[风格规范](style.md)中的可用字体；补齐实际内容与所需页码后检查渲染。
颜色和布局可以改，字段名和类型不能自行发明。

已有图片时，用一个 `image` 元素替换 `evidence-frame` 和 `missing-evidence`：
设置唯一 `elementId`、`bounds: [48, 140, 540, 300]`、`src: media/figure.png`、
`fit: {mode: contain}`。删掉旧元素时也删除对应 `allowedOverlaps` 声明。图片必须
真实存在于项目内；说明和来源保留为独立原生文字。

注意：

- `bounds` 是 `[x, y, width, height]`，不是四边坐标。
- 元素数组按从后到前的层级排列。背景形状与其标签可以有意重叠，无关文字不应碰撞。
- 原生文字不支持元素级 opacity、rotation 或 flip，需用支持的表达或说明图片替代。
- 包含 `:`、`#`、HTML 的文字使用 JSON 序列化、引号或 YAML 块标量，不粘贴 TypeScript 类型声明。
- 校验入口是清单，不是单独页面。独立 Skill 使用 `python3 scripts/ansatz_slide.py validate <project>`，
  导出使用 `python3 scripts/ansatz_slide.py deck export <project> -o output.pptx`。
