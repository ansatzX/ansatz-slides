# 图示制作：Matplotlib、TikZ 与 VectorCraft

本附录负责把已确定的图示需求制作成素材，再放入 `page.yaml`。内容判断与来源要求见
[内容 guide](../content.md#按讲解需要补齐页面元素)，配色和字体沿用[唯一风格](../style.md)。
先读共同规则，再读所选路线；用 VectorCraft 前必须读取本机命令目录。

## 按图的用途选择路线

| 图的主要任务 | 默认路线 | 应保留的源文件 |
| --- | --- | --- |
| 从实验或计算数据展示趋势、比较、分布、误差 | Matplotlib 等数据绘图 package | 原始数据、处理与绘图脚本、PNG，按需 SVG／PDF |
| 精确几何、数学关系、推导配图或结构明确的学术示意 | TikZ | `.tex`、PDF、用于 PPTX 的 PNG |
| 模型、架构、流程、机制等需要矢量对象和后续手工调整的示意 | VectorCraft | `.vectorcraft`、命令 JSON 或构建脚本、PNG，按需 SVG |

按表达需要选择，不要求一张图经过三种工具。用户明确选择时遵从用户；某一路线缺失
时可选择另一路合适的方法，不能把数据图改成没有数据依据的装饰示意。VectorCraft
制作图，Deckcraft 创建／渲染 PPTX，两者的命令和依赖不能混用。

## 共同规则：依据、尺寸与插图

1. 先明确图要回答什么、有哪些对象或系列、连接表示什么。数据图的结论来自真实
   数据；示意图的关系来自已核实的论文、官方文档或对应版本代码。仅有 README 或
   模型名不足以恢复内部架构，必要时追到实际调用和数据流。新增解释与原文结果区分。
2. 按目标页面中图的 `bounds` 和长宽比制作。字、线和符号以插入 PPTX 后的大小检查，
   不能只看放大后的独立图。不要继承外部技能的固定色板、9.5 pt 字号、艺术隐喻或
   固定画布；让布局表达比较、层次、流向或几何关系。
3. 可复用数据、图稿、脚本和输出放在源项目内，如 `data/`、`figures/model/`、
   `media/`。本仓库内工作项目放在 `tmp/`；缓存和编译中间文件也放 `tmp/`。
   不依赖另一台机器的绝对路径、私人 helper 或历史图稿，不改用户全局环境。
4. 默认插入清晰 PNG；有透明背景需求时实际导出透明素材。SVG／PDF 可作为矢量交付，
   使用 SVG 插入时另查目标软件兼容性。外部源图可编辑不代表嵌入的图片能在 PPTX 内
   逐个对象编辑。公式按[公式路线](equations.md)从表达式排版，不由绘图工具猜公式。
5. 图片就绪后复制到项目内，在页面使用稳定 `elementId`、真实相对 `src`、
   `fit: {mode: contain}` 与目标 `bounds`；记录数据、版本、引用及必要的简化说明。
   仍缺数据或图示依据时按[占位规则](../production.md#素材准备与可替换占位)保留位置。
   替换占位后清理原文字与失效重叠声明，重新导出并检查实际 PPTX。

## Matplotlib：依据数据作图

先读数据字段、单位、分组、取样与误差含义，决定横纵轴和图型，核实本页结论是否
得到支持。保留缺失值与预处理说明，不为得到预设趋势而筛选或重写数据；误差条、
拟合、归一化和对数轴需要明确含义。不能凭正文结论生成伪装成实测的点或曲线。

使用已有可用 Python 环境；缺依赖时只在项目环境准备，不全局安装。无窗口绘图
采用 `Agg` 后端，并显式设置缓存目录，避免在用户配置目录或系统临时目录落盘：

```bash
mkdir -p tmp/mpl-cache tmp/test-tmp
MPLCONFIGDIR="$PWD/tmp/mpl-cache" TMPDIR="$PWD/tmp/test-tmp" \
  python ./deck/figures/result/build_plot.py
```

`python` 代表已确认有 Matplotlib 的解释器；项目使用 uv 时用该项目的 `uv run`。
脚本用相对自身位置解析输入与输出，至少保留这一结构：

```python
from pathlib import Path
import csv
import matplotlib
matplotlib.use("Agg")  # 在导入 pyplot 前设置
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
with (root / "data.csv").open(newline="", encoding="utf-8") as stream:
    rows = list(csv.DictReader(stream))
x = [float(row["x"]) for row in rows]
y = [float(row["y"]) for row in rows]
# x、y 列名、单位及比较对象必须按实际数据调整。
plt.rcParams.update({"font.family": "Arial", "font.size": 16})
fig, ax = plt.subplots(figsize=(7.2, 3.6), layout="constrained")
ax.plot(x, y, "o-", color="#2C68B0")
ax.set_xlabel("x")
ax.set_ylabel("y")
fig.savefig(root / "result.png", dpi=240)
fig.savefig(root / "result.svg")
plt.close(fig)
```

示例只是输入与导出结构，没有给任何科学结论。字体、画幅、坐标单位、是否适合连线
及字号应按真实数据与最终放置尺寸决定。中文标签显式配置已安装的微软雅黑／黑体，
检查缺字和字体替换；不能用删除中文标签规避。`dpi`、像素数和独立图好看均不能代替
PPTX 中的可读性。SVG 需要转轮廓时另行处理，并保留可重新生成文字的脚本。

## TikZ：精确几何与数学示意

检查所需工具与宏包，不假设另一台机器的 TeX 安装相同：

```bash
command -v xelatex pdftocairo
kpsewhich tikz.sty
kpsewhich standalone.cls
```

用 `.tex` 保存节点、连线、坐标和数学表达式。采用 `standalone` 按图稿边界生成 PDF，
例如下面只表达一个输入到模型的概念关系，不是特定 ML 模型的真实结构：

```latex
\documentclass[tikz,border=8pt]{standalone}
\usepackage{fontspec}
\setmainfont{Arial}
\setsansfont{Arial}
\usetikzlibrary{arrows.meta,positioning}
\definecolor{accent}{HTML}{780373}
\begin{document}
\begin{tikzpicture}[font=\sffamily\large,>=Stealth,node distance=30mm]
\node[draw=accent,thick,minimum width=24mm,minimum height=12mm] (x) {Input $x$};
\node[draw=accent,thick,right=of x,minimum width=32mm,minimum height=12mm] (f) {Model $f(x)$};
\draw[->,thick,accent] (x) -- (f);
\end{tikzpicture}
\end{document}
```

```bash
mkdir -p tmp/tex-build tmp/test-tmp
TMPDIR="$PWD/tmp/test-tmp" xelatex -no-shell-escape \
  -interaction=nonstopmode -halt-on-error -output-directory tmp/tex-build \
  ./deck/figures/model/model.tex
pdftocairo -png -singlefile -transp -r 240 \
  tmp/tex-build/model.pdf ./deck/media/model
```

该示例使用 XeLaTeX；纯数学且不需 `fontspec` 时可以采用 pdfLaTeX，但应调整导言区。
中文节点先确认 `xeCJK` 等所需宏包可用，显式设置推荐中文字体，不直接套用 macOS
字体名。只有少量短标签时，也可在上述 XeLaTeX 示例中用 `fontspec` 明确指定字体：

```latex
% 导言区：确认本机已有该字体
\newfontfamily\figurezh{Microsoft YaHei}
% 节点内容示例
% \node ... {\figurezh 输入 $x$};
```

此方式已用于本机短中文节点试作，不替代复杂中文段落的断行和排版支持。
检查编译错误、缺字与裁边；确认 PDF／PNG 中箭头、数学符号及标签完整。
保留 `.tex` 与 PDF，编译日志不是正式素材。只需一个公式时优先用现有公式脚本。

## VectorCraft：生成与手工编辑衔接

本节由用户提供的 VectorCraft 控制绘图方法适配而来。Linux 本机在 0.16.0 核对并
试作过；其他环境仍先检查实际版本与命令 schema，不假定命令数量或旧参数固定。
无需依赖 `/Applications`、`/Users`、`vc_edit.py` 或另一电脑的目录。

可手动编辑是选择 VectorCraft 的重要理由。CLI 适合批量构建和导出；GUI 适合直接
查看画布、调整布局、文字与连线。按任务使用任一方式，也可以先由 Agent 生成，
再打开窗口由用户继续修改；不要求无窗口运行。始终保留 `.vectorcraft` 原生图稿。

### 能力发现

```bash
command -v vectorcraft-cli vectorcraft
vectorcraft-cli --version
vectorcraft-cli --help
mkdir -p tmp/vectorcraft
vectorcraft-cli commands > tmp/vectorcraft/commands.json
```

以 `engine.commands`／CLI 目录里的 `params` 为准，用结构化解析或 `rg` 查所需命令，
不把旧文档中的参数直接当成本机事实。目录中 `enabled: false` 可能只是当前没有打开
文档；先区分状态限制与命令缺失。字体、导入和导出警告都必须实际检查。

### 新建图稿：headless JSON 批处理

`vectorcraft-cli run` 不需要 GUI 或控制端口，接收 JSON 数组或 JSON Lines。
先编写命令文件，保留它或生成它的 `build_*.py`。下面是概念示意的最小结构：

```json
[
  {"command":"file.new","params":{"name":"Model diagram","width":640,"height":220,"units":"Pixels","backgroundContents":"white"}},
  {"command":"shape.rectangle","params":{"x":40,"y":60,"width":180,"height":90}},
  {"command":"paint.setFill","params":{"ids":["$1.id"],"color":"#F3F6FA"}},
  {"command":"text.create","params":{"x":130,"y":115,"text":"Input data","font":"Arial","size":22,"justify":"center","color":"#202020"}},
  {"command":"shape.rectangle","params":{"x":420,"y":60,"width":180,"height":90}},
  {"command":"paint.setFill","params":{"ids":["$4.id"],"color":"#F8F2F8"}},
  {"command":"text.create","params":{"x":510,"y":115,"text":"Model output","font":"Arial","size":22,"justify":"center","color":"#202020"}},
  {"command":"shape.line","params":{"x1":240,"y1":105,"x2":400,"y2":105}},
  {"command":"stroke.set","params":{"ids":["$7.id"],"weight":2,"endArrow":"Arrow","arrowAlign":"tip"}},
  {"command":"document.inspect","params":{}},
  {"command":"text.fonts","params":{}}
]
```

`$1.id` 引用第 1 步（从 0 开始）创建对象的返回 ID，不是恒定对象编号；调整命令顺序
时一并调整引用。此 JSON 结构是 CLI 批处理格式，不能原样发到 TCP 协议端口。

```bash
vectorcraft-cli run --commands ./deck/figures/model/commands.json \
  --export ./deck/figures/model/model.vectorcraft \
  --export ./deck/figures/model/model.svg \
  --export ./deck/media/model.png --scale 2
vectorcraft-cli info ./deck/figures/model/model.vectorcraft
```

`--scale` 设置栅格输出的每 point 像素数，不修改 SVG 的对象大小；不要把像素尺寸
与 PPTX `bounds` 混用。SVG 默认不保证文字转轮廓；需要时明确生成轮廓版本：

```bash
vectorcraft-cli convert ./deck/figures/model/model.vectorcraft \
  ./deck/figures/model/model-outlined.svg --outline-text
```

检查退出状态、每步 JSON 结果及导出 `warnings`，打开 PNG 检查。`.vectorcraft` 保存
可供 GUI 手改的源对象；转轮廓 SVG 不再保留可编辑文字，不能只留下它而丢掉源稿。
需要人工接续时，在 VectorCraft 窗口中打开该原生图稿。手动修改后保存原稿，再重新
导出 PPTX 引用的图片；画布保存不会自动更新已插入 PPTX 的图片。

### 增量修改与对象语义

保留用户在画布中的手工调整时，使用 `run --in 原稿.vectorcraft` 或打开原文档，
按对象修改并导出候选。先 `document.find` 再 `document.node` 确认对象，检查命中数，
不要用一次子串匹配直接改所有结果。通过 `object.setProps` 的 `name`／`data` 设置
稳定标签，保存与复核后再按授权范围替换旧稿。整体参数化几何变化才重跑构建脚本；
不为了挪一个标签从零重建整张图。

| 操作 | 应注意的本机协议语义 |
| --- | --- |
| `shape.rectangle`、`shape.ellipse` | `x,y` 为左上角，不是圆心 |
| `text.create` | 普通点文字的 `y` 是基线；可用 `justify: center` 对齐 x，再复核返回 bounds |
| `stroke.set` | 箭头用 `endArrow` 与 `arrowAlign: tip`，不猜 `arrowEnd` 等别名 |
| `object.setBounds` | 当前版本作用于选区，不接受 `ids`；先 `select.none`、`select.add`，再指定 `reference: 0` 等确切语义 |
| `document.find` | 本机目录列出 name／kind／text 子串及 limit；不沿用旧电脑未核实的 exact／within 等过滤参数 |
| `text.setText` | 文字改变可能重排尺寸；检查新 bounds、居中及邻接连线 |
| `object.group` | 复核分组后的层级，避免背景遮住未入组的文字或箭头 |
| `document.save`／`file.saveAs` | 显式指定 path 与 format，不能把仅返回 dataBase64 当成已写盘 |
| `text.fonts` | 检查 missing、substitute 及 missingGlyphs；“有文字对象”不证明字形显示正确 |

### 需要操作运行中 GUI 时：JSON 控制端口

需要查看、交互绘图或衔接手工编辑时，可以直接使用 GUI；Agent 需要控制运行中画布
时使用此端口分支，用户手工编辑本身不要求控制端口。检查本机进程及目标端口，
需启动时使用本机找到的 `vectorcraft --control 7979`，端口可按任务调整。服务不随
skill 加载自动启动；不要因端口不通就杀掉用户实例，尤其不能沿用旧文档的全局 pkill。
新图或候选文件只写到当前源项目内，不写私人日志目录或自动更新用户记忆。

TCP 通道每行一个 JSON 请求和回复，核对 `id` 与 `ok`。一般引擎命令通过
`engine.execute`；`engine.commands`、`ui.inspect` 为顶层方法。最小客户端如下：

```python
import json
import socket

class VC:
    def __init__(self, port=7979):
        self.socket = socket.create_connection(("127.0.0.1", port), timeout=30)
        self.reader = self.socket.makefile("r", encoding="utf-8")
        self.request_id = 0

    def direct(self, method, params=None):
        self.request_id += 1
        request = {"id": self.request_id, "method": method, "params": params or {}}
        self.socket.sendall((json.dumps(request, ensure_ascii=False) + "\n").encode())
        line = self.reader.readline()
        if not line:
            raise RuntimeError("VectorCraft disconnected; inspect state before retrying")
        reply = json.loads(line)
        if reply.get("id") != self.request_id or not reply.get("ok"):
            raise RuntimeError(reply)
        return reply.get("result")

    def cmd(self, name, params=None):
        return self.direct("engine.execute", {"command": name, "params": params or {}})

    def close(self):
        self.reader.close()
        self.socket.close()
```

图形坐标、样式和文件格式仍以该实例的目录为准。超时后先查文档实际状态，不能盲目
重放创建或保存命令造成重复对象。GUI/TCP 分支未由 CLI 无窗口试作证明。

## 检查与交付

独立图稿先检查内容、数据、箭头方向、层级、标签、公式、字体与裁边；再查看它在
实际 PPTX 中的尺寸、对比度和可读性。曲线或复杂几何有定量约束时用代码检查相应
关系，不能用对象数、统计词数或空 warnings 代替看图。

交付实际引用的 PNG 及可继续修改的源：Matplotlib 数据与脚本，TikZ `.tex`／PDF，
VectorCraft `.vectorcraft`／命令文件或构建脚本。按[引用规则](../content.md#参考文献与外部补充)
在使用图的页面呈现短引文，完整来源与制作方法同时写入页面 notes；缺图
继续明确占位及未完成状态。统一按[审阅与交付](../review.md)验收最终 PPTX。
