# 技术参考

本规范说明演示文稿清单（`pptx.yaml`）和页面对象（`*.page.yaml`）。Python 会校验这些 YAML 源文件并导出 PPTX。任意 PPTX 文件都无法无损转换回这些源文件。

## 如何使用本参考文档

首次编写先看[制作与最小示例](production.md#最小示例)，再通过[工作对象](production/cli.md)创建或更新正式源文件。正式 YAML 中的注释需要 YAML 解析器；候选文件仍接受纯 JSON 语法。按实际使用的字段或元素查阅本文档，无需从头通读。TypeScript 接口用于描述类型，不是可执行的页面文件。标记为“不支持”的章节表示输入不受支持，不得输出。如果正文与严格校验器不一致，应停止并解决差异；绝不可放宽校验来迁就正文。


本文描述 native 后端的字段与底层默认值；新稿应显式采用[学术风格](style.md)的推荐值。可选 Deckcraft 后端仅接受[列出的子集](production/cli.md#deckcraft-创建后端)，不能把本文全部字段视为两个后端都支持。


### 字段查阅入口

编写源文件必须读[全局约定](#1-全局约定)、[清单](#3-主入口文件pptxyaml)、
[页面](#4-页面文件pageyaml)和[元素基类](#elementbase元素基类)，再查实际使用的元素：
[文本](#text文本框)、[形状](#shape形状)、[图片](#image图片)、
[表格](#table表格)、[图表](#chart图表)。元素引用的颜色、字体、填充、边框等类型见
[共享类型](#2-共享类型)。未使用的元素和动画章节无需通读。

---

## 本文档约定
- 使用 **TS 接口**描述结构，并配以**字段表**和**最小 YAML 示例**帮助理解
- **默认值**在 TS 行尾注释中标为 `// default: X`。X 可以是字面值（`1` / `"top"` / `[0, 0]`），也可以是描述性短语（`not applied` / `not shown` / `falls back along the inheritance chain` / `auto-adapts to chart size` 等）
- **约束**在 TS 行尾注释或 TS 代码块下方标为 `// constraint: ...`，统一使用区间或不等式表示法（`[0, 1]` / `> 0`），或使用文字说明
---

## 1. 全局约定

### 语法
- 使用受限的 YAML 语法，并采用类似 YAML 1.2 的标量处理方式。拒绝重复键、合并键、递归别名和非字符串映射键；未加引号的 `on`、`off`、`yes`、`no` 仍按字符串处理。
- 对于 `:`、`#`、`{`、`}` 等特殊字符，值必须加引号，或改用块标量
- 对于 `content.text` 等包含许多特殊字符的字段，应将块标量（`|`）单独作为一个块使用，以免 `style="..."` 之类的内容被错误解析

### 坐标系与单位
- 所有几何和尺寸单位均为 **px**；原点 `(0, 0)` 位于页面左上角
- 默认演示文稿尺寸：16:9 → `[960, 540]`；4:3 → `[720, 540]`。默认海报尺寸：16:9 → `[1280, 720]`；9:16 → `[720, 1280]`；4:3 → `[1280, 960]`；3:4 → `[960, 1280]`；1:1 → `[1080, 1080]`
- 本规范定义 1px = 1pt（即 `fontSize: 18` 在 PPTX 中为 18pt）
- 元素叠放顺序由 `Page.elements` 数组中的顺序决定；越靠后的元素图层越高

### 样式优先级与默认值

属性值发生冲突时，按下列优先级从上到下查找第一个已设置值；如果各层级均未设置，则使用本节末尾的默认值。

> 本节所有子节均适用以下规则：`lineHeight`（倍数）与 `lineHeightPx`（固定 px）互斥；两者同时设置时，以 `lineHeightPx` 为准。

#### 1. 文本框内的文本样式

**优先级顺序：**
1. [Text.content.text](#textcontent文本内容) 中的 `<u>`、`<sup>`、`<strong>` 等富文本语义标签
2. 在 `<span style="...">` 中设置的行内属性
3. 在 `<p style="...">` 中设置的段落属性
4. **直接设置在 [Text.content](#textcontent文本内容) 上的样式字段**（不同于 `style` 所引用的主题样式；包括 `color`、`fontSize`、`fontFamily`、`bold`、`italic`、`backgroundColor`、`lineHeight`、`lineHeightPx`、`letterSpacing`、`marginTop`）
5. [Text.content.style](#textcontent文本内容) 引用的 [TextStyleConfig](#textstyleconfig文本样式配置) 主题样式
6. 默认值：

| 属性 | 默认值 |
|---|---|
| color | `#000000` |
| backgroundColor | 不应用 |
| fontSize | `18` |
| fontFamily | `"MiSans"` |
| bold | `false` |
| italic | `false` |
| lineHeight | `1` |
| lineHeightPx | 不应用 |
| letterSpacing | `0` |
| marginTop | `0` |

#### 2. 表格单元格样式

**优先级顺序：**
1. [Cell.text](#cell单元格) 中的 `<u>`、`<sup>`、`<strong>` 等富文本语义标签
2. 在 `<span style="...">` 中设置的行内属性
3. 在 `<p style="...">` 中设置的段落属性
4. [Cell](#cell单元格) 行内字段
5. [Cell.textStyle](#cell单元格) 引用的 [TextStyleConfig](#textstyleconfig文本样式配置)（**仅应用于文本字段**；不包括 `fill` / `border` / `align`）
6. [TableStyleConfig](#tablestyleconfig表格样式配置) 的位置类别样式
   - 行与列样式冲突时，由 [TableStyleConfig.rowOverColumn](#tablestyleconfig表格样式配置) 决定优先项；默认 `true` 表示行样式优先
   - 行类别：`TableStyleConfig.firstRowStyle` / `TableStyleConfig.lastRowStyle`
   - 列类别：`TableStyleConfig.firstColumnStyle` / `TableStyleConfig.lastColumnStyle`
7. [TableStyleConfig.bodyStyles](#tablestyleconfig表格样式配置)：应用于首行和末行以外的数据行，并按数据行索引循环使用
8. [TableStyleConfig.cellStyle](#tablestyleconfig表格样式配置)：整张表的基础单元格样式
9. 默认值

| 属性 | 默认值 |
|---|---|
| color | `#000000` |
| backgroundColor | 不应用 |
| fontSize | 根据单元格高度自动适配 |
| fontFamily | `"MiSans"` |
| bold | `false` |
| italic | `false` |
| lineHeight | `1` |
| lineHeightPx | 不应用 |
| letterSpacing | `0` |
| marginTop | `0` |
| fill | 不应用（透明） |
| border | `{style: solid, width: 1, color: "#000000"}` |
| align | `["center", "middle"]` |

#### 3. 图表样式

图表涉及多种样式（系列主体颜色、字体、数据标签、坐标轴/图例可见性等），每种都有独立的优先级顺序，说明如下。

**3.1 系列主体颜色优先级：**
1. 系列显式设置的 `fill` / `lineColor` / `areaColor`（字段名因类型而异；参见[颜色机制](#52-颜色机制)）
2. [Chart.seriesDefaults](#seriesdefaults系列默认值) 中对应类型的同名字段
3. [Theme.colors](#theme主题) 主题颜色循环（按系列在数组中的出现顺序取色）

> [scatter](#scatter散点图) 是例外：标记颜色按 `marker.fill > series.fill > 主题颜色循环` 解析；`marker.border` 同样优先于 `series.border`。
>
> 各类型的具体颜色字段、派生规则和角色映射见[§5.2 颜色机制](#52-颜色机制)。

**3.2 字体优先级：**
1. 子组件的 `fontFamily`（[TitleConfig](#titleconfig标题配置) / [LegendConfig](#legendconfig图例配置) / [DataLabelConfig](#datalabelconfig数据标签配置) / [AxisConfig.label](#axisconfig坐标轴配置) / [SpokeAxisConfig.label](#spokeaxisconfig辐射轴配置)）
2. [Chart.fontFamily](#chart图表-1)
3. 主题默认字体（[Theme](#theme主题) 或 PPTX 母版字体）

**3.3 dataLabels 优先级：**
1. `series[i].dataLabels`
2. [Chart.dataLabels](#chart图表-1)（全局默认值）
3. 不显示（等同于 `show: false`）

> 子字段采用**单层浅合并**：`series.dataLabels` 仅覆盖其显式提供的子字段；未提供的字段回退到 [Chart.dataLabels](#chart图表-1)；若两处均未提供，则采用该类型的默认值（参见 [dataLabels.content 值速查](#55-datalabelscontent-值速查)）。

**3.4 `seriesDefaults` 合并规则：**

[Chart.seriesDefaults](#seriesdefaults系列默认值)`[type]` 为该类型的所有系列提供通用默认值，并与各系列执行**单层深合并**：
- **标量字段**（字符串 / 数字 / 布尔值）：系列显式值覆盖默认值
- **对象字段**（`marker` / `dataLabels` / `border` / `upBars` / `downBars` / `totalBars` / 渐变 `fill` 对象等）：递归进行单层浅合并——默认值与系列中的同名字段分别展开，子字段由更近的来源覆盖
- **数组字段**（`fill: []` / `colorScheme: []`）：系列整体替换默认值，不逐项合并
- `seriesDefaults` 内不允许出现 `type` 和 `encode`
- 仅多系列类型支持 `seriesDefaults`：`bar / line / area / scatter / bubble / radar`

反直觉示例：
```yaml
seriesDefaults:
  bar: {marker: {shape: circle, size: 8}}
series:
  - type: bar
    marker: {size: 12}     # after merge: {shape: circle, size: 12}, not {size: 12}
```

**3.5 `boolean | Config` 字段约定：**

`boolean | XxxConfig` 形式的字段（`marker` / `legend` / `AxisConfig.label / axisLine / gridLine` / `SpokeAxisConfig.label / axisLine / gridLine` / `colorbar`）统一遵循以下规则：
- `false` = 关闭
- `true` = 使用默认配置开启
- 对象 `{...}` = 使用自定义配置开启

> **唯一例外**：[scatter.marker](#scatter散点图) 不能为 `false`（没有标记的散点图无法绘制任何内容）。

---

### 多文件结构
一个 pptx.yaml 项目由主入口文件和各页面文件组成：
```
project/
  pptx.yaml     # main entry (size/theme/title + page reference list)
  media/               # media resources such as images and videos
  pages/               # page file directory
    1_cover.page.yaml       # one .page.yaml file per page
    2_intro.page.yaml
```
**路径规则：**
1. **本地文件必须位于项目内**：所有本地引用都必须解析到清单所在文件夹内；不允许引用项目外的本地文件。远程素材另有支持，但因此不能无条件声称离线可用或完全自包含。
2. **本地路径均为相对路径**（相对于清单所在目录）：
   - `pptx.yaml` 中的 `pages` 列表：`pages/1_cover.page.yaml`
   - `.page.yaml` 中的图片路径：`media/image1.jpg`
3. **素材支持 URL**：`Image.src` 以及背景/填充的图片填充源可使用 HTTP(S) 或 data URL；本地解析支持 PNG/JPEG/GIF/SVG。为保证交付可复现，优先使用已核实的本地素材。URL 可用性及 SVG 在目标软件中的显示效果仍需检查。

**必须提供主入口**：向 `validate` / `export` 传入清单（或仅包含一个清单的目录）；单独的页面 YAML 文件不是完整输入。

---

## 2. 共享类型
以下类型会在多处复用，因此集中定义。元素章节按类型名称引用，不再重复展开定义。

### Color（颜色）
```ts
type Color = string;
```
> 支持不透明 **HEX6**（`#RRGGBB`）、带透明度的 **HEX8**（`#RRGGBBAA`）以及 [Theme.colors](#theme主题) 主题颜色引用（如 `$primary`）。

### FontFamily（字体族）
```ts
type FontFamily = string | { latin: string; ea: string };
```
| 形式 | 示例 | 说明 |
|------|------|------|
| 字符串 | `"MiSans"` | 中英文统一使用同一种字体 |
| 对象 | `{latin: "Arial", ea: "MiSans"}` | 分别明确指定西文字体（latin）和东亚字体（ea） |

字体选择与创作默认值见[字体与层级](style.md#字体与层级)，制作时显式填写。下方及默认值表中的 MiSans 是底层省略字段时的兼容回退值，不是当前风格的推荐字体。

> **字体：**字体族名称用于在目标应用程序中选择字体。Python 导出器不会嵌入字体；请确认西文和东亚字体均可用，并检查渲染结果。

### Alignment（对齐方式）
```ts
type HorizontalAlign = "left" | "center" | "right" | "justify" | "distributed";
type VerticalAlign   = "top"  | "middle" | "bottom";
type Alignment       = [HorizontalAlign, VerticalAlign];
```
| 值 | 说明 |
|----|------|
| `left` / `center` / `right` | 水平左对齐 / 居中 / 右对齐 |
| `justify` | 两端对齐（末行不拉伸） |
| `distributed` | 分散对齐（末行也拉伸） |
| `top` / `middle` / `bottom` | 垂直顶部 / 居中 / 底部对齐 |

### LineStyle（线型）
```ts
type LineStyle = "solid" | "dash" | "dot";
```

### Border（边框）
```ts
interface Border {
  style?: LineStyle;  // default: "solid"
  width?: number;     // default: 1
  color?: Color;      // default: "#000000"
}
```

#### BorderSpec（边框规格）
[Cell](#cell单元格) 和 [CellStyle](#cellstyle单元格样式) 支持使用 `Border` 数组形式，分别设置四条边框。

```ts
type BorderSpec = null
                | Border
                | [Border | null, Border | null]
                | [Border | null, Border | null, Border | null, Border | null];
```

| 形式 | 含义 |
|------|------|
| `null` | 显式清除：四边均无边框（用于覆盖继承链上更高层设置的边框） |
| `Border` | 四边使用相同边框 |
| 二元素数组 `[Border\|null, Border\|null]` | `[上-下, 左-右]` |
| 四元素数组 `[Border\|null, Border\|null, Border\|null, Border\|null]` | `[上, 右, 下, 左]`（顺时针） |

> 数组内的 `null` 表示对应位置无边框；顶层的 `null` 会清除所有边框。

### Shadow（阴影）

```ts
interface Shadow {
  blur: number;                // blur radius
  color: Color;
  offset?: [number, number];   // default: [0, 0]; [x, y] offset
}
```

### ColorStop（颜色停止点）

```ts
interface ColorStop {
  position: number;  // constraint: [0, 1]
  color: Color;
}
```

### ImageFit / ImageCrop（图片适配 / 裁剪）

```ts
interface ImageFit {
  mode: "fill" | "contain" | "cover";
}

interface ImageCrop {
  left?: number;
  top?: number;
  right?: number;
  bottom?: number;
}
```

> **约束：**`ImageCrop` 的四个字段含义相似，默认值均为 0。正值按比例从对应边缘向内裁切（内缩）；负值按比例向外扩展并以透明像素补齐（外扩）。必须保证 `left + right < 1` 且 `top + bottom < 1`，否则源矩形会退化。

| ImageFit.mode | 说明 |
|---|---|
| `cover` | 填满容器并保持宽高比，可能裁切 |
| `contain` | 完整显示图片并保持宽高比，可能留白 |
| `fill` | 拉伸至填满容器，可能变形 |

### Fill（填充）

```ts
type Fill = SolidFill | GradientFill | ImageFill;

interface SolidFill {
  type: "solid";
  color: Color;
}

interface GradientFill {
  type: "gradient";
  gradientType: "linear" | "radial";
  stops: ColorStop[];                // constraint: at least 2
  angle?: number;                    // default: 0; only effective for linear
}

interface ImageFill {
  type: "image";
  src: string;                       // URL or relative path
  fit?: ImageFit;                    // default: {mode: "cover"}
  crop?: ImageCrop;                  // always applied; see the rendering order with fit below
  opacity?: number;                  // default: 1; constraint: [0, 1]
}
```

> `GradientFill.angle` 的取值范围为 `[0, 360)`；`0` 表示从左至右，角度顺时针递增。例如：`90` = 上→下，`180` = 右→左。

> **ImageFill 渲染顺序：**`crop`（按比例调整源矩形：正值向内裁切，负值向外扩展并以透明像素补齐）→ `fit`（按模式适配填充容器）。各 `fit.mode` 值的具体语义与 [Image](#image图片) 章节中的“渲染逻辑”说明一致。

**示例：**

```yaml
# Solid
fill:
  type: solid
  color: "$primary"

# Gradient
fill:
  type: gradient
  gradientType: linear
  angle: 90
  stops:
    - {position: 0, color: "$primary"}
    - {position: 1, color: "$accent"}

# Image
fill:
  type: image
  src: "media/bg.jpg"
  fit: {mode: cover}
  opacity: 0.9
```

---

## 3. 主入口文件（pptx.yaml）

### Presentation（演示文稿）

```ts
interface Presentation {
  version: "v2";                // required, fixed to "v2" (version identifier)
  title?: string;              // default: no title
  customFonts?: CustomFont[];  // optional metadata; fonts are not downloaded or embedded
  size: [number, number];      // [width, height]; see "Coordinate System and Units" for PPT and poster recommendations
  theme?: Theme;
  pages: string[];             // list of relative paths to page files, e.g. "pages/cover.page.yaml"
}
```

**示例：**

```yaml
version: v2
title: Annual Work Summary
size: [960, 540]
theme:
  colors:
    primary: "#2563EB"
    accent: "#F59E0B"
    text: "#1F2937"
  textStyles:
    title:
      fontSize: 40
      color: "$primary"
    body:
      fontSize: 18
      color: "$text"
      lineHeight: 1.6
  tableStyles:
    default:
      firstRowStyle:
        fill: {type: solid, color: "$primary"}
        color: "#ffffff"
        bold: true
      bodyStyles:
        - {fill: {type: solid, color: "#f8fafc"}}
        - {fill: {type: solid, color: "#ffffff"}}
pages:
  - pages/1_cover.page.yaml
  - pages/2_content.page.yaml
```

### Theme（主题）

主题集中管理颜色、文本样式和表格样式。在相关字段中使用 `$<key>` 引用主题：

| 主题类型 | 引用字段 | 示例 |
|---|---|---|
| `colors` | 任意 [Color](#color颜色) 字段 | `$primary` |
| `textStyles` | [TextContent.style](#textcontent文本内容) / [Cell.textStyle](#cell单元格) | `$title` |
| `tableStyles` | [Table.style](#table表格) | `$default` |

```ts
interface Theme {
  colors?: Record<string, Color>;
  textStyles?: Record<string, TextStyleConfig>;
  tableStyles?: Record<string, TableStyleConfig>;
}
```

#### TextStyleConfig（文本样式配置）

```ts
interface TextStyleConfig {
  color?: Color;
  fontSize?: number;
  fontFamily?: FontFamily;
  bold?: boolean;                    // bold
  italic?: boolean;                  // italic
  backgroundColor?: Color;           // text background color (e.g., text highlight)
  lineHeight?: number;               // line-height multiple
  lineHeightPx?: number;             // fixed line height (px); when it conflicts with lineHeight, lineHeightPx prevails
  letterSpacing?: number;
  marginTop?: number;
}
```

> 未设置的字段沿继承链回退（详情见[样式优先级与默认值](#样式优先级与默认值)）。

#### CellStyle（单元格样式）

```ts
interface CellStyle extends TextStyleConfig {
  // —— Inherits all properties of TextStyleConfig ——
  //   color / fontSize / fontFamily / bold / italic / backgroundColor / lineHeight / lineHeightPx / letterSpacing / marginTop

  // —— CellStyle-specific ——
  fill?: Fill;                              // background fill
  border?: BorderSpec;                      // border
  align?: Alignment;                        // text alignment
}
```

> 未设置的字段沿继承链回退（详情见[样式优先级与默认值](#样式优先级与默认值)）。

#### TableStyleConfig（表格样式配置）

```ts
interface TableStyleConfig {
  // —— Cell style: applied to every cell ——
  cellStyle?: CellStyle;

  // —— Row category overrides ——
  firstRowStyle?: CellStyle;  // first-row style
  lastRowStyle?: CellStyle;  // last-row style

  // —— Column category overrides ——
  firstColumnStyle?: CellStyle;
  lastColumnStyle?: CellStyle;

  // —— Alternating row styles ——
  bodyStyles?: CellStyle[];  // data rows other than the first/last row apply these cyclically by data-row index

  // —— Cross-category rule ——
  rowOverColumn?: boolean;            // default: true; whether the row style wins when a cell is covered by both row and column rules
}
```
> **行/列样式规则**：`firstRowStyle` / `lastRowStyle` / `firstColumnStyle` / `lastColumnStyle` 等类别样式表示**分别应用于每个匹配的单元格**，而不是整体应用于首行/末列。
> - 设置 `firstRowStyle.border: {style: solid, width: 2}` → **首行的每个单元格**四边都会加上边框
> - 若要为首行整体添加外框，请使用逐边 BorderSpec：`border: [<top line>, null, <bottom line>, null]`，再分别为首行首列和末列的单元格设置边框


> 回退规则见[样式优先级与默认值](#样式优先级与默认值)。

### CustomFont（自定义字体）

```ts
interface CustomFont {
  family: string;  // font family name for use in fontFamily fields
  src: string;     // Google Fonts CSS URL; format: https://fonts.googleapis.com/css2?family=Noto+Serif+SC; only the default weight is supported — weight selection is not supported
}
```

---

## 4. 页面文件（*.page.yaml）

### Page（页面）

```ts
interface Page {
  pageType?: "cover" | "table_of_contents" | "chapter" | "content" | "final" | string;  // default: none; category label (does not affect rendering); preset values are recognized as the corresponding page type, arbitrary custom strings are also allowed
  background?: Fill;               // default: {type: solid, color: "#FFFFFF"} (white solid fill)
  notes?: string;                  // default: none; speaker notes; plain text
  elements: Element[];             // the later an element, the higher its layer
  animations?: Animation[];        // default: none; orchestrated in array order; see [Animations](#6-动画)
}
```

**示例：**

```yaml
pageType: cover
background:
  type: solid
  color: "$primary"
notes: Speaker notes
elements:
  - elementId: title1
    elementType: text
    bounds: [100, 200, 760, 80]
    content:
      style: "$title"
      align: [center, middle]
      text: Hello World
```

---

## 5. 元素

### ElementBase（元素基类）

所有元素共有的属性。

```ts
interface ElementBase {
  elementId: string;                                                      // constraint: unique within the same page; unique element ID
  elementType: "text" | "shape" | "line" | "image" | "icon" | "table" | "chart";  // element type
  bounds: [number, number, number, number];                               // element size and position, [x, y, width, height]
}

type Element = Text | Shape | Line | Image | Icon | Table | Chart;
```

---

### Text（文本框）

```ts
interface Text extends ElementBase {
  elementType: "text";
  content: TextContent;
}
```

文字元素不支持 `rotation`、`opacity` 或 `flip`，校验器会拒绝这些字段。
需要此类效果时使用合适的图片素材并保留可编辑源稿。

#### TextContent（文本内容）

```ts
interface TextContent {
  text: string;                                // rich text string (block scalar)
  style?: string;                              // references theme.textStyles, written as "$key" (e.g. "$title")

  // —— Style fields (when unset, fall back along the inheritance chain) ——
  color?: Color;
  fontSize?: number;
  fontFamily?: FontFamily;
  bold?: boolean;                              // bold: true=on, false/unset=off
  italic?: boolean;                            // italic: true=on, false/unset=off
  backgroundColor?: Color;                     // text background color (e.g., text highlight)
  lineHeight?: number;                         // line-height multiple
  lineHeightPx?: number;                       // fixed line height (px)
  letterSpacing?: number;
  marginTop?: number;

  // —— Layout fields ——
  textDirection?: "horizontal" | "vertical";   // default: "horizontal"
  wrap?: boolean;                              // default: true; when false, no wrapping, and the part beyond bounds.width overflows the element boundary; explicitly setting false is recommended for single-line text
  align?: Alignment;                           // default: ["left", "top"]

  // —— Visual decoration (unset = not applied) ——
  gradient?: GradientFill;                     // text gradient (applied to the text itself)
  shadow?: Shadow;                             // text shadow
}
```

**示例：**

```yaml
# Basic: theme style + plain text
- elementId: title-1
  elementType: text
  bounds: [100, 50, 760, 80]
  content:
    style: "$title"
    align: [center, middle]
    text: Annual Work Summary

# Rich text + inline property overrides
- elementId: body-1
  elementType: text
  bounds: [100, 200, 600, 200]
  content:
    fontSize: 20
    color: "$text"
    lineHeight: 1.6
    align: [left, top]
    text: |
      <p><strong>Key achievement</strong>: completed <span style="color:$primary;">3</span> key projects</p>
      <p style="text-align:right"><span style="font-size:14px; color:#6b7280;">—— FY2024</span></p>

# Text gradient + shadow
- elementId: hero-text
  elementType: text
  bounds: [100, 100, 760, 120]
  content:
    align: [center, middle]
    gradient:
      type: gradient
      gradientType: linear
      angle: 90
      stops:
        - {position: 0, color: "$primary"}
        - {position: 1, color: "$accent"}
    shadow:
      blur: 6
      color: "#00000040"
      offset: [0, 3]
    text: |
      <p><span style="font-size:64px;">FUTURE</span></p>
```

#### 富文本规则

`TextContent.text` 和 `Cell.text` 遵循下列富文本规则，用于拆分段落以及设置段落或行内样式。

**支持的标签**

| 标签 | 说明 | 示例 |
|------|------|------|
| `<p>` | 段落；可携带段落样式 | `<p>paragraph</p>` |
| `<span>` | 行内样式；使用此标签设置行内样式 | `<span style="color:#f00">red</span>` |
| `<strong>` | 粗体 | `<strong>important</strong>` |
| `<em>` | 斜体 | `<em>emphasis</em>` |
| `<u>` | 下划线 | `<u>underline</u>` |
| `<s>` | 删除线 | `<s>deleted</s>` |
| `<sup>` | 上标 | `E=mc<sup>2</sup>` |
| `<sub>` | 下标 | `H<sub>2</sub>O` |
| `<a>` | 超链接；支持 `https://`、`http://`、`mailto:`；设置后会自动应用超链接文本样式（蓝色并带下划线） | `<a href="https://x.com">link</a>` |
| `<ul>` | 无序列表 | `<ul><li>item</li></ul>` |
| `<ol>` | 有序列表 | `<ol><li>first item</li></ol>` |
| `<li>` | 列表项；必须与 `<ul>` 或 `<ol>` 配合使用 | — |

**style 属性映射**

`<p>`、`<li>` 和 `<span>` 可以使用 `style="..."`。所有颜色类型的值均可使用主题引用（如 `$primary`），并按 [Color](#color颜色) 规则解析。

1. **段落样式（仅 `<p>` 支持）**

| 属性 | 说明 | 值 | 示例 |
| --- | --- | --- | --- |
| `text-align` | 段落水平对齐方式 | `left` / `center` / `right` / `justify` / `distributed` | `<p style="text-align:center">…</p>` |
| `line-height` | 行高；**不带单位**时视为 `lineHeight` 倍数，**带 `px`** 时视为 `lineHeightPx` 固定值 | 数字（如 `1.5`）或 px 字符串（如 `24px`） | `<p style="line-height:1.6">…</p>` |
| `margin-top` | 段前间距 | px 字符串（如 `8px`） | `<p style="margin-top:8px">…</p>` |
| `margin-left` | 左边距 | px 字符串（如 `12px`） | `<p style="margin-left:12px">…</p>` |
| `margin-right` | 右边距 | px 字符串（如 `12px`） | `<p style="margin-right:12px">…</p>` |

> 不要在 `<p>` 上设置 `letter-spacing`；若要统一设置字间距，请使用 `content.letterSpacing` 或 `Cell.letterSpacing`。

2. **列表项样式（仅 `<li>` 支持）**

| 属性 | 说明 |
| --- | --- |
| `text-align` | 列表项水平对齐方式 |
| `line-height` | 行高；值规则同 `<p>` |
| `letter-spacing` | 字间距 |
| `margin-top` | 段前间距 |
| `margin-left` | 左边距 |

`list-style*` CSS 属性会被拒绝；请使用 `<ul>` 或 `<ol>` 指定受支持的圆点或十进制标记。不会静默忽略自定义标记样式。
支持的圆点或十进制标记。自定义标记样式不会被静默忽略。

3. **行内样式（仅 `<span>` 支持）**

样式仅应用于该 `<span>` 内的文本。

| 属性 | 说明 | 值 | 示例 |
| --- | --- | --- | --- |
| `color` | 文本颜色 | [Color](#color颜色)（HEX6 / HEX8 / 主题引用） | `<span style="color:$primary">…</span>` |
| `font-size` | 字号 | px 字符串（如 `24px`） | `<span style="font-size:24px">…</span>` |
| `font-family` | 字体族 | 字体名称（如 `Arial`、`"Arial, 微软雅黑"`） | `<span style="font-family:Arial">…</span>` |
| `letter-spacing` | 额外字间距 | px 字符串 | `<span style="letter-spacing:1px">…</span>` |
| `font-style` | 斜体样式 | `normal` / `italic` / `oblique`（倾斜体） | — |
| `text-decoration` | 装饰线 | `none`、`underline`、`line-through`，或后两者同时使用 | — |
| `background-color` | 文本背景色 | [Color](#color颜色)（HEX6 / HEX8 / 主题引用） | `<span style="background-color:$accent">…</span>` |


```yaml
content:
  align: [left, top]
  lineHeight: 1.2
  text: |
    <p><span style="font-size:32px; color:$primary;">Main Title</span><span style="font-size:18px; color:$secondary;">Subtitle</span></p>
    <p style="text-align:center; line-height:1.8">This paragraph is center-aligned with 1.8x line height</p>
    <p style="text-align:right">This paragraph is right-aligned; line height inherits the default 1.2</p>
```
**纯文本简写**

`content.text` 可以直接使用纯文本：
- 单行：`text: "Hello"` ≡ `text: "<p>Hello</p>"`
- 多行（块标量）：
  ```yaml
  text: |
    First line
    Second line
  ```
  ≡ `<p>First line</p><p>Second line</p>`
- `<br/>` 会在同一段落中导出明确的 DrawingML 换行。需要分成不同段落时使用 `<p>`。

**LaTeX 公式**

公式制作路线见[制作附录](production/equations.md)。本节仅说明原始导出的语法能力；受检流程对原生 Office Math 的限制仍然适用。

富文本通过 `\(...\)` 定界符支持**有限的 LaTeX 到 Office Math 子集**。它不是完整的 TeX 引擎：未知命令会保留为字面文本。关于不支持的表达式和最终渲染检查，见[公式处理路径](production/equations.md)。

- 公式可以独占一个段落，也可以与其他文本混排在 `<p>` 中。
- 公式内部**不允许**富文本标签。
- 公式**只继承**上下文中的 `color` 和 `font-size` 样式；其他文本样式不会传入。
- 可以用 `<p>` 标签包裹 LaTeX 公式以控制对齐方式。

```yaml
content:
  text: |
    <p>Pythagorean theorem: \(a^2 + b^2 = c^2\)</p>
    <p>\(\int_0^1 x^2 \mathrm{d}x = \frac{1}{3}\)</p>
```

---

### Shape（形状）

```ts
interface Shape extends ElementBase {
  elementType: "shape";
  rotation?: number;                  // default: 0; degrees, clockwise rotation
  opacity?: number;                   // default: 1; constraint: [0, 1]
  flip?: [boolean, boolean];          // default: [false, false]; [horizontal flip, vertical flip]
  shapeName: string;                  // see technical/shapes.md
  adjustments?: number[];             // see technical/shapes.md; geometry parameters; default: the default parameter values
  viewBox?: [number, number];         // view box; used only when shapeName="custom", required in that case
  path?: string;                      // SVG shape path; used only when shapeName="custom", required in that case
  fill?: Fill;                        // default: not applied
  border?: Border;                    // default: not applied
  shadow?: Shadow;                    // default: not applied
}
```

> 自定义形状：可指定 `shapeName: "custom"`，并使用 `viewBox` 和 `path` 定义形状；当 `shapeName` 不是 `custom` 时，这两个参数无效。

> `adjustments` 参数：沿用 OOXML 定义的参数顺序和数量；取值约束见 technical/shapes.md。

> **注意：**`shape` 不支持嵌入文本！如需文本，请额外添加文本框。

**自定义路径约定：**
- `viewBox`：视图框，即路径坐标系 `[w, h]`
- `path`：SVG 路径字符串，支持 `M / L / H / V / C / S / Q / A / Z` 命令。
- 支持挖空等形状的多段路径：外轮廓应为**顺时针**（`sweep=1`），内轮廓应为**逆时针**（`sweep=0`），从而形成镂空部分。
- **缩放与宽高比**：更改 `bounds` 会调整形状大小（无需重写路径）；但 `viewBox` 会分别拉伸以适配边界框，宽高比不同时形状会变形。若要保持比例，需满足 `viewBoxW : viewBoxH = bounds.w : bounds.h`。

**常见形状**

> 完整的 177 种形状见 [shapes.md](technical/shapes.md)。

| shapeName | 说明 | adjustments 默认值 |
|-----------|------|-------------------|
| `rect` | 矩形 | — |
| `roundRect` | 圆角矩形 | `[16667]`（圆角半径） |
| `ellipse` | 椭圆 | — |
| `triangle` | 三角形 | `[50000]`（顶点的水平位置） |
| `diamond` | 菱形 | — |
| `homePlate` | 五边形箭头 | `[50000]` |
| `chevron` | V 形箭头 | `[50000]` |
| `donut` | 圆环 | `[25000]`（环宽比例） |
| `star5` | 五角星 | `[19098, 105146, 110557]` |
| `rightArrow` | 右箭头 | `[50000, 50000]`（箭杆宽度、箭头长度） |
| `wedgeRectCallout` | 矩形标注框 | `[-20833, 62500]` |
| `bracePair` | 成对大括号 | `[8333]` |

**示例：**

```yaml
# Built-in shape
- elementId: shape-1
  elementType: shape
  bounds: [200, 200, 300, 150]
  shapeName: roundRect
  adjustments: [20000]
  fill: {type: solid, color: "$primary"}
  border: {style: solid, width: 2, color: "$accent"}

# Custom hollow ring (outer contour clockwise + inner contour counterclockwise)
- elementId: shape-2
  elementType: shape
  bounds: [400, 200, 150, 150]
  shapeName: custom
  viewBox: [1000, 1000]
  path: "M500,0 A500,500 0 1 1 499,0 Z M500,200 A300,300 0 1 0 499,200 Z"
  fill: {type: solid, color: "$accent"}
```

---

### Line（线条）

```ts
type ArrowType = "arrow" | "stealth" | "diamond" | "oval";

interface Line extends ElementBase {
  elementType: "line";
  rotation?: number;                             // default: 0; degrees, clockwise rotation
  opacity?: number;                              // default: 1; constraint: [0, 1]
  flip?: [boolean, boolean];                     // default: [false, false]; [horizontal flip, vertical flip]
  viewBox: [number, number];                     // path coordinate system [w, h]; points live in this coordinate system, so changing bounds does not require changing points
  points: string;                                // bezier path points "x1,y1 x2,y2 ..."; the first/last points are the start/end the curve passes through, the middle points are control points
  curve?: "sharp" | "round" | "smooth";          // default: "round"; sharp joins / rounded joins / bezier smooth curve
  arrow?: [ArrowType | null, ArrowType | null];  // start arrow, end arrow; default: [null, null] (no arrows at either end)
  border?: Border;                               // default: not applied
  shadow?: Shadow;                               // default: not applied
}
```

> **约束：**`points` 至少需要 2 个点；首点和末点是曲线经过的点，其余为贝塞尔控制点；所有坐标都必须位于 `viewBox` 内。
> **viewBox 与 bounds：**渲染时，`viewBox` 会分别拉伸以适配边界框尺寸；若要避免线条变形，需满足 `viewBoxW : viewBoxH = bounds.w : bounds.h`。

**示例：**

```yaml
# Normalized coordinates: from top-left to bottom-right, the two middle points are control points
- elementId: l4
  elementType: line
  bounds: [100, 100, 500, 300]
  viewBox: [1, 1]
  points: "0,0 0.2,0 0.8,1 1,1"
  curve: smooth
  border: {style: solid, width: 2, color: "$primary"}

# Bezier arc: passes through the start and end points; the two middle points control the bend direction
- elementId: bezier-arc
  elementType: line
  bounds: [50, 200, 860, 100]
  viewBox: [360, 100]
  points: "0,80 120,0 240,100 360,20"
  curve: smooth
  border: {style: solid, width: 2, color: "$primary"}
```

---

### Image（图片）

```ts
interface Image extends ElementBase {
  elementType: "image";
  rotation?: number;                 // default: 0; degrees, clockwise rotation
  opacity?: number;                  // default: 1; constraint: [0, 1]
  flip?: [boolean, boolean];         // default: [false, false]; [horizontal flip, vertical flip]
  src: string;                       // URL or local relative path
  cropShape?: ShapeDef;              // default: rectangle (i.e., no shape cropping)
  fit?: ImageFit;                    // default: {mode: "cover"}
  crop?: ImageCrop;                  // always applied; see the rendering order with fit/cropShape below
  border?: Border;                   // default: not applied
  shadow?: Shadow;                   // default: not applied
}

interface ShapeDef {
  shapeName: string;                 // see technical/shapes.md; use "custom" for a custom path
  adjustments?: number[];            // default: use the shape's built-in defaults (see technical/shapes.md)
  viewBox?: [number, number];        // used only when shapeName="custom", required in that case
  path?: string;                     // used only when shapeName="custom", required in that case
}
```

> `ShapeDef` 字段与 [Shape](#shape形状) 元素的形状字段一一对应；详细约定（adjustments 值和角度换算、自定义路径规则、镂空规则、常见形状表）见 [Shape](#shape形状) 一节。

> **渲染逻辑：**`crop`（按比例调整源矩形以截取子图：正值向内裁切，负值向外扩展并以透明像素补齐）→ `fit`（按模式将子图适配到边界框容器）→ `cropShape`（将最终显示区域裁剪为形状轮廓）。三者可以分别设置，并严格按上述顺序应用。

- `fit.mode="cover"`：按比例缩放子图以填满边界框；超出部分会被裁切。
- `fit.mode="contain"`：按比例缩放子图以完整显示；未填满的部分留空。
- `fit.mode="fill"`：**直接拉伸子图以填满边界框**——此模式下虽不会看到裁切后留下的空边，但图片内容仍只是裁剪后的子区域，而非完整原图。

**示例：**

```yaml
- elementId: img-1
  elementType: image
  bounds: [50, 50, 400, 300]
  src: "media/cover.jpg"
  cropShape: {shapeName: roundRect, adjustments: [15000]}
  fit: {mode: cover}
  crop: {top: 0.1, bottom: 0.1, left: 0.05, right: 0.05}   # crop the surrounding proportions first, then apply cover fitting
  shadow:
    blur: 10
    color: "#00000033"
    offset: [0, 4]

# Custom clip outline
- elementId: img-2
  elementType: image
  bounds: [200, 200, 200, 200]
  src: "media/avatar.jpg"
  cropShape:
    shapeName: custom
    viewBox: [1000, 1000]
    path: "M500,0 A500,500 0 1 1 499,0 Z"
  fit: {mode: cover}
```

---

### Icon（图标）

```ts
interface Icon extends ElementBase {
  elementType: "icon";
  rotation?: number;                 // default: 0; degrees, clockwise rotation
  opacity?: number;                  // default: 1; constraint: [0, 1]
  flip?: [boolean, boolean];         // default: [false, false]; [horizontal flip, vertical flip]
  iconName: string;                  // format "style:name"
  fill?: Fill;                       // default: black solid fill
  border?: Border;                   // default: not applied
  shadow?: Shadow;                   // default: not applied
}
```

**iconName 格式：**`style:name`，使用 Font Awesome 7.x 免费图标库。

| 前缀 | 样式 | 示例 |
|------|------|------|
| `fas` | 实心（最常见） | `fas:house` |
| `far` | 常规 | `far:heart` |
| `fab` | 品牌 | `fab:github` |

图标搜索： https://fontawesome.com/search?ic=free-collection

> **图标渲染：**Python 写入器会将图标名称存入私有 `k:icon` 扩展，并输出一个通用的可编辑备用形状。标准演示应用可能只显示该备用形状。若必须显示实际图标图稿，请使用提供的图片；`icon` 元素不保证生成原生可编辑图标图稿。

**示例：**

```yaml
- elementId: icon-1
  elementType: icon
  bounds: [100, 100, 48, 48]
  iconName: "fas:lightbulb"
  fill: {type: solid, color: "$primary"}
```

---

### Table（表格）

> 本节描述字段兼容范围；常用素材制作方式见[制作与修改](production.md)。

```ts
interface Table extends ElementBase {
  elementType: "table";
  columnWidths: number[];              // array of column-width ratios (not px; relative to the bounds width)
  rowHeights: number[];                // array of row-height ratios (not px; relative to the bounds height)
  rows: Cell[][];                      // 2-D array; merged regions are declared with rowSpan/colSpan, occupied positions are skipped in the array
  style?: string | TableStyleConfig;   // references theme.tableStyles, written as "$key" (e.g. "$default"), or an inline TableStyleConfig object
  fill?: Fill;                         // default: not applied; table-level fill (applied to the whole table, can be overridden by cell fill)
  shadow?: Shadow;                     // default: not applied
}
```

> **PowerPoint 限制：**原生表格不能整体旋转或翻转；也不支持包含文本和边框在内的整表全局透明度。若需要整体旋转、翻转或透明度，应先渲染为图片，再作为 [Image](#image图片) 元素处理。

> **约束：**`columnWidths` 和 `rowHeights` 的每一项均须在 `[0, 1]` 范围内，且各自的元素之和均为 1。

#### Cell（单元格）

```ts
interface Cell {
  // —— Content ——
  text?: string;             // default: empty cell; rich text string (written as a block scalar), rules same as TextContent.text
  textStyle?: string;        // references theme.textStyles, written as "$key" (e.g. "$body")

  // —— Text styles (when unset, fall back along the inheritance chain) ——
  color?: Color;
  fontSize?: number;
  fontFamily?: FontFamily;
  bold?: boolean;
  italic?: boolean;
  backgroundColor?: Color;             // text background color (e.g., text highlight)
  lineHeight?: number;                 // line-height multiple
  lineHeightPx?: number;               // fixed line height (px)
  letterSpacing?: number;
  marginTop?: number;

  // —— Cell styles (when unset, fall back along the inheritance chain) ——
  fill?: Fill;                         // background fill; supports solid / gradient / image
  border?: BorderSpec;
  align?: Alignment;

  // —— Merging ——
  rowSpan?: number;                    // default: 1
  colSpan?: number;                    // default: 1
}
```

**基础示例（使用主题样式）：**

```yaml
- elementId: table-basic
  elementType: table
  bounds: [80, 120, 800, 280]
  columnWidths: [0.3, 0.35, 0.35]
  rowHeights: [0.33, 0.33, 0.34]
  style: "$default"
  rows:
    - - text: "Metric"
      - text: "2023"
      - text: "2024"
    - - text: "Revenue (100M CNY)"
      - text: "82.5"
      - text: "96.3"
    - - text: "Net profit (100M CNY)"
      - text: "12.1"
      - text: "15.8"
```

> **合并单元格规则：**`rowSpan` / `colSpan` 声明合并范围；**合并区域覆盖的单元格应从 `rows` 数组中省略，无需以 `null` 占位**。例如，左上角单元格合并为 2×2 后，第 0 行的 colSpan=2 覆盖 (0,1)，因此该行只包含两个项（(0,0) 合并单元格和 (0,2)）；第 1 行的 (1,0) 和 (1,1) 被合并区域占用，因此只包含一个项 (1,2)。

```yaml
- elementId: table-merged
  elementType: table
  bounds: [100, 100, 600, 400]
  columnWidths: [0.33, 0.33, 0.34]
  rowHeights: [0.33, 0.33, 0.34]
  rows:
    # Row 0: top-left 2×2 merge + C1. The merged (0,1) is omitted
    - - text: "Merged cell"
        fill: {type: solid, color: "$accent"}
        rowSpan: 2
        colSpan: 2
      - text: "C1"
    # Row 1: (1,0) and (1,1) are occupied by the merge → only C2 remains
    - - text: "C2"
    # Row 2: full three columns
    - - text: "A3"
      - text: "B3"
      - text: "C3"
```

---

### Chart（图表）

> 本节描述字段兼容范围；常用素材制作方式见[制作与修改](production.md)。

图表顶层没有 `type` 字段；每个 `series[i].type` 决定其图表形式。Python 校验器接受以下八种系列类型：

`bar` / `line` / `area` / `scatter` / `bubble` / `pie` / `radar` / `waterfall`

> **不支持的图表类型：**`candlestick`、`heatmap`、`treemap`、`sunburst` 和 `sankey` 会在导出前被拒绝。请在外部制作这些可视化，再作为图片放置。

每种类型都在其子节首行声明**系列约束**：同一图表中允许的最大数量，以及它可以与哪些其他类型共存。

#### Chart（图表）

```ts
interface Chart extends ElementBase {
  elementType: "chart";

  data: ChartData;                            // required
  series: SeriesConfig[];                     // required; constraint: length ≥ 1
  seriesDefaults?: SeriesDefaults;            // default: not applied; common defaults grouped by series.type, merged with each series

  // —— Cartesian coordinate system (conditionally effective by series.type, see §5.3) ——
  xAxis?: AxisConfig | AxisConfig[];          // default: auto-adapt to data; in array form, referenced via series[i].xAxisIndex
  yAxis?: AxisConfig | AxisConfig[];          // default: auto-adapt to data; in array form, referenced via series[i].yAxisIndex
  barWidth?: number;                          // default: adaptive; constraint: (0, 1]; bar width / category slot width ratio
  barGap?: number;                            // default: 0 (flush); constraint: [0, 1); gap between bars when multiple bar series are grouped
  categoryGap?: number;                       // default: 0.2; constraint: [0, 1); blank ratio between category slots

  // —— Radar coordinate system (radar series only) ——
  spokeAxis?: SpokeAxisConfig;                // default: auto-adapt to data; spoke axes + spider grid

  // —— Global components ——
  title?: string | TitleConfig;               // default: no title
  legend?: boolean | LegendConfig;            // default: varies by type (see the default-value table in [LegendConfig](#legendconfig图例配置))
  dataLabels?: DataLabelConfig;               // default: not applied; global default, can be overridden by series.dataLabels
  fontFamily?: FontFamily;                    // default: falls back along the theme/master fonts

  // —— Chart frame (controls the rectangular container of the whole chart element, independent of series colors) ——
  fill?: Fill;                                // default: not applied
  border?: Border;                            // default: not applied
  shadow?: Shadow;                            // default: not applied
}

type SeriesConfig =
  | BarSeries | LineSeries | AreaSeries | ScatterSeries | BubbleSeries
  | CandlestickSeries | PieSeries | RadarSeries | WaterfallSeries
  | HeatmapSeries | TreemapSeries | SunburstSeries | SankeySeries;
```

> `fill` / `border` / `shadow` 控制**图表元素的矩形框架**（作用于整个图表容器），与系列主体颜色相互独立。
>
> **PowerPoint 限制：**原生图表不能整体旋转或翻转；也没有能够覆盖“整个图表（包括标题、坐标轴、图例、标签和系列）”的单一全局透明度属性。若需要整体旋转、翻转或透明度，请先渲染为图片，再作为 [Image](#image图片) 元素处理。

#### ChartData（图表数据）

```ts
interface ChartData {
  cols: string[];                                   // column names; constraint: unique, non-empty strings
  rows: (number | string | null)[][];               // constraint: each row's length = cols.length
}
```

> **数据完整性约束**（ansatz-slide 严格校验器会针对可执行图表类型进行校验）：
> - `cols` 中出现重复列名 → `DuplicateColumnError`
> - `cols` 中含有空字符串 → `EmptyColumnError`
> - `rows[i].length !== cols.length` → `RowLengthError`
> - encode 引用的列名不在 `cols` 中 → `UnknownColumnError`
> - 多个系列引用同一列是合法的（例如，同一个 y 列同时绘制为柱形和折线）
> - 数值通道（`y` / `value` / `open` / `high` / `low` / `close` / `size` / `flow`）的列值若为字符串，会尝试解析为数字；解析失败时抛出 `NonNumericValueError`
>
> **缺失单元格的写法：**填入 `null`，例如 `[null, null, 2, 3]`。不建议使用连续逗号（`[, , 2, 3]`）——严格 YAML 解析器会报错。

#### 通用规则

1. **系列的 `fill` 类型：**`Color | GradientFill`；字符串按纯色 [Color](#color颜色) 处理（HEX8 或 `$xxx` 主题引用），对象按 [GradientFill](#fill填充) 处理（其中 `type: "gradient"`）；部分类型支持 `(Color | GradientFill)[]` 数组形式（按切片/节点循环取值）。**系列级填充不支持 [ImageFill](#fill填充)**。
2. **类型混用：**图表的 `series[]` 可包含哪些类型，由各类型章节首行的“系列约束”决定；严格校验器会据此强制执行受支持的范围。
3. **有条件生效的顶层字段：**`xAxis` / `yAxis` / `barWidth` / `barGap` / `categoryGap` / `spokeAxis` 属于**坐标系级**配置，其生效与否取决于 `series[].type` 集合（详情见[5.3 图表顶层字段的适用范围](#53-图表顶层字段的适用范围)）。
4. **[Color](#color颜色) 主题引用范围：**所有 `Color` 类型字段（包括嵌套数组和对象中每个 Color 值）都支持 `$xxx` 主题引用，例如 `upBars: {fill: "$success"}`、`colorScheme: ["$bg", "$primary"]`、`fill: ["$primary", "$accent"]`。
5. **可选对象类型字段的省略语义：**所有标记为 `?` 的**对象类型**字段（`xAxis` / `yAxis` / `spokeAxis` / `colorScale` / `marker` / `dataLabels` 等），省略时等同于空配置 `{}`，各子字段均采用自己的默认值——也就是说，“坐标轴/网格/标签等仍会按默认设置渲染，只是参数由系统自动推断”。这不同于 [ElementBase](#elementbase元素基类) 的 `fill` / `border` / `shadow`（省略表示**不应用**）。

> **bar / waterfall 方向：**由坐标轴类型决定——`xAxis.type === "category"` 时为纵向（默认），`yAxis.type === "category"` 时为横向。默认根据数据列推断 `axis.type`（字符串 → category，数字 → value）；若数值列需要用作类别（如年份），应显式指定 `axis.type: "category"`。横向图中，`encode.x` 引用数值列，`encode.y` 引用类别列，`numberFormat` 写在数值轴所在的一侧。对 scatter / bubble 而言，x 和 y 都是数值通道，不存在方向概念。

---

#### TextStyle（文本样式）

```ts
interface TextStyle {
  color?: Color;            // default: falls back along the inheritance chain (theme text color / PPTX master)
  fontSize?: number;        // default: auto-adapts to chart size
  fontFamily?: FontFamily;  // default: falls back along the inheritance chain to Chart.fontFamily or the theme font
}
```

> 供 [TitleConfig](#titleconfig标题配置) / [LegendConfig](#legendconfig图例配置) / [DataLabelConfig](#datalabelconfig数据标签配置) / [AxisConfig](#axisconfig坐标轴配置).label / [SpokeAxisConfig](#spokeaxisconfig辐射轴配置).label 继承和复用的通用三项文本样式；字体优先级见 [§3.2](#3-图表样式)。

#### LineStyleConfig（线型配置）

```ts
interface LineStyleConfig {
  style?: "solid" | "dash" | "dot";    // default: "solid"
  color?: Color;                       // default: falls back to the theme
  width?: number;                      // default: 1
}
```

> 通用线型配置，由 [AxisConfig](#axisconfig坐标轴配置) / [SpokeAxisConfig](#spokeaxisconfig辐射轴配置) 的 `axisLine` / `gridLine` 复用。

#### TitleConfig（标题配置）

```ts
interface TitleConfig extends TextStyle {
  text: string;                        // required
  // fontSize auto-adapts to chart size by default
}
```

#### LegendConfig（图例配置）

```ts
interface LegendConfig extends TextStyle {
  show?: boolean;                      // default: varies by type (see the table below)
  position?: "top" | "bottom" | "left" | "right";  // default: "bottom"
}
```

`show` 的类型默认值：

| 类型 | 默认值 |
|---|---|
| bar / line / area / scatter / bubble / pie / radar | `true` |
| waterfall | `false` |

> `legend: false` 或 `legend: {show: false}` 会关闭图例，**对受支持类型有效**；`legend: true` 或对象形式只会对上表中标记为适用的类型产生视觉效果。

#### DataLabelConfig（数据标签配置）

```ts
interface DataLabelConfig extends TextStyle {
  show?: boolean;                      // default: false
  content?: "value" | "percentage" | "category";  // default: varies by type (see [5.5 value quick reference](#55-datalabelscontent-值速查))
  numberFormat?: string;               // default: no formatting; Excel number-format string (see below)
}
```

> **numberFormat 标准：**支持 Excel 数字格式字符串的一个子集——`0`（整数）/ `0.0`（一位小数）/ `0%`（百分比）/ `0.0%`（含小数的百分比）/ `#,##0`（千位分隔符）/ `0.0E+00`（科学计数法）。不支持 `[Red]` 颜色区段、负数区段和条件格式等高级语法。

#### MarkerConfig（标记配置）

```ts
interface MarkerConfig {
  shape?: "circle" | "rect" | "diamond" | "triangle";  // default: "circle"
  fill?: Color | GradientFill;         // default: follows the series body color
  border?: Border;                     // default: not applied
  size?: number;                       // default: auto-adapts to chart size; unit px
}
```

> `rect` 命名与 [shapes.md](technical/shapes.md) 形状库保持一致。

#### AxisConfig（坐标轴配置）

```ts
interface AxisConfig {
  show?: boolean;                      // default: true
  type?: "category" | "value";         // default: inferred from the data column (string → category, number → value)
  min?: number;                        // default: auto-adapt to data; only effective for value axes
  max?: number;                        // default: auto-adapt to data; only effective for value axes
  reverse?: boolean;                   // default: false; true = reverse the axis direction (maximum at the origin side)
  title?: string | TitleConfig;        // default: no title; the string form is recommended, use the object only for special styling
  label?: boolean | (TextStyle & {     // default: true; tick labels
    numberFormat?: string;             // default: no formatting; only effective for value axes
  });
  axisLine?: boolean | (LineStyleConfig & {  // default: true
    arrow?: boolean | "start" | "end" | "both";  // default: false; true is equivalent to "end"
  });
  gridLine?: boolean | LineStyleConfig;     // default: true
}
```

#### SeriesDefaults（系列默认值）

```ts
interface SeriesDefaults {
  bar?: Partial<Omit<BarSeries, "type" | "encode">>;
  line?: Partial<Omit<LineSeries, "type" | "encode">>;
  area?: Partial<Omit<AreaSeries, "type" | "encode">>;
  scatter?: Partial<Omit<ScatterSeries, "type" | "encode">>;
  bubble?: Partial<Omit<BubbleSeries, "type" | "encode">>;
  radar?: Partial<Omit<RadarSeries, "type" | "encode">>;
}
```

> 为该类型的所有系列提供通用默认值，避免在多个系列中重复设置。合并算法和适用类型范围见 [§3.4](#3-图表样式)。

#### SpokeAxisConfig（辐射轴配置）

仅用于 [radar](#radar雷达图) 系列。

```ts
interface SpokeAxisConfig {
  show?: boolean;                      // default: true
  min?: number;                        // default: 0; minimum of the value axis shared by all dimensions
  max?: number;                        // default: auto-adapt to data; maximum of the value axis shared by all dimensions
  label?: boolean | (TextStyle & {     // default: true; tick labels
    numberFormat?: string;             // default: no formatting
  });
  axisLine?: boolean | LineStyleConfig;     // default: true; spoke lines from the center to the outer ring
  gridLine?: boolean | LineStyleConfig;     // default: true; spider grid lines (concentric polygons connecting the spoke endpoints)
}
```

#### LinearSeriesBase（线性系列基类）

由 [line](#line折线图) / [area](#area面积图) / [radar](#radar雷达图) 共享的曲线类通用字段。

```ts
interface LinearSeriesBase {
  smooth?: boolean;                                   // default: false
  lineStyle?: "solid" | "dash" | "dot";               // default: "solid"
  width?: number;                                     // default: 2
  marker?: false | MarkerConfig;                      // default: not applied
  nullHandling?: "zero" | "gap" | "connect";          // default: "gap" for line/area, "connect" for radar
  lineColor?: Color | GradientFill;                   // default: follows the theme color cycle; line color of line / polygon stroke color of area+radar
}
```

> 如果同一图表中的多个 line/area/radar 系列设置了不同的 `nullHandling` 值，则仅**第一个非空值**生效，其他系列均沿用该值；不支持多个空值处理方式。

---

#### bar（柱形图）

> **系列约束：**可与 `line / area / scatter / bubble` 任意混用；同一图表中的 bar 系列数量不限。

```ts
interface BarSeries {
  type: "bar";
  encode: { x: string; y: string };    // required
  name?: string;                       // default: the encode.y column name; for legend display only
  xAxisIndex?: number;                 // default: 0; meaningful only when chart.xAxis is an array
  yAxisIndex?: number;                 // default: 0; meaningful only when chart.yAxis is an array
  stack?: "value" | "percent";         // default: no stacking; "value" sums directly, "percent" normalizes to 100%
  symbol?: ShapeDef;                   // default: normal rectangular bar; pictographic bar shape definition (see [ShapeDef](#image图片))
  fill?: Color | GradientFill;         // default: follows the theme color cycle
  border?: Border;                     // default: not applied
  dataLabels?: DataLabelConfig;        // default: not shown; content only takes "value"
}
```

#### line（折线图）

> **系列约束：**可与 `bar / area / scatter / bubble` 任意混用。

```ts
interface LineSeries extends LinearSeriesBase {
  type: "line";
  encode: { x: string; y: string };    // required
  name?: string;                       // default: the encode.y column name
  xAxisIndex?: number;                 // default: 0
  yAxisIndex?: number;                 // default: 0
  dataLabels?: DataLabelConfig;        // default: not shown; content only takes "value"
}
```

> line 没有区域，因此不提供 `fill`；其他曲线类字段见 [LinearSeriesBase](#linearseriesbase线性系列基类)。

#### area（面积图）

> **系列约束：**可与 `bar / line / scatter / bubble` 任意混用。

```ts
interface AreaSeries extends LinearSeriesBase {
  type: "area";
  encode: { x: string; y: string };    // required
  name?: string;                       // default: the encode.y column name
  xAxisIndex?: number;                 // default: 0
  yAxisIndex?: number;                 // default: 0
  stack?: "value" | "percent" | "stream";  // default: no stacking; "stream" = streamgraph (area only)
  areaColor?: Color | GradientFill;    // default: derived from lineColor as semi-transparent
  dataLabels?: DataLabelConfig;        // default: not shown
}
```

> **堆叠组规则：**同一图表中，**所有设置了 `stack` 的同类型系列会自动归为一个堆叠组**，无需显式组标识。同一图表中每种类型最多支持一个堆叠组——所有设置了 `stack` 的系列必须使用相同值（全部为 `"value"` / `"percent"` / `"stream"`）；混用会抛出 `StackModeMismatchError`；未设置 `stack` 的系列独立显示。若需要多个独立堆叠组，请拆分为多个图表元素。
>
> **`stream` 仅适用于 area：**按 `value` 归一化并偏移中心基线；堆叠区域在 y=0 上下对称，形成“河流图”形状。

#### scatter（散点图）

> **系列约束：**可与 `bar / line / area / bubble` 任意混用。

```ts
interface ScatterSeries {
  type: "scatter";
  encode: { x: string; y: string };    // required; each series references its own x/y column pair
  name?: string;                       // default: the encode.y column name
  yAxisIndex?: number;                 // default: 0
  dataFilter?: { col: string; value: string | number };  // default: no filtering; optional: group with a long table
  marker?: MarkerConfig;               // default: {shape: "circle"}; constraint: cannot be false
  fill?: Color | GradientFill;         // default: follows the theme color cycle; serves as the marker's default fill color (marker.fill takes precedence)
  border?: Border;                     // default: not applied; serves as the marker's default border (marker.border takes precedence)
  dataLabels?: DataLabelConfig;        // default: not shown; content only takes "value"
}
```

#### bubble（气泡图）

> **系列约束：**可与 `bar / line / area / scatter` 任意混用。

```ts
interface BubbleSeries {
  type: "bubble";
  encode: { x: string; y: string; size: string };  // required
  name?: string;                       // default: the encode.y column name
  yAxisIndex?: number;                 // default: 0
  dataFilter?: { col: string; value: string | number };  // default: no filtering; rows where the col column equals value are used as this series' data
  sizeScale?: "linear" | "sqrt" | "log";  // default: "sqrt"
  sizeRange?: [number, number];        // default: auto-adapts to chart size; bubble radius range in px
  fill?: Color | GradientFill;         // default: follows the theme color cycle; bubble fill color
  border?: Border;                     // default: not applied
  dataLabels?: DataLabelConfig;        // default: not shown; content only takes "value"
}
```

> **sizeScale：**`sqrt`（默认）使面积与 size 成正比；`linear` 使半径与 size 成正比；`log` 适合数量级差异较大的场景。负 size 按 0 处理。若要显示多组数据，请使用宽表并用 null 补齐；每个系列引用各自的 `x/y/size` 列组合。

#### candlestick（蜡烛图）

Python 校验器会拒绝此类型。请在外部制作该可视化，再作为图片放置。

#### pie（饼图）

> **系列约束：**`series` 数组只能有 1 个元素，且不得与其他类型共存。

```ts
interface PieSeries {
  type: "pie";
  encode: { category: string; value: string };  // required
  innerRadius?: number;                // default: 0; constraint: [0, 1]; > 0 = donut
  startAngle?: number;                 // default: 0 (12 o'clock direction)
  fill?: Color | GradientFill | (Color | GradientFill)[];   // default: follows the theme color cycle; an array cycles by slice
  border?: Border;                     // default: not applied
  dataLabels?: DataLabelConfig;        // default: not shown; content takes "value" | "percentage" | "category", default "value"
}
```

> **角度方向：**固定为**顺时针为正**；0° = 12 点钟方向，90° = 3 点钟方向，180° = 6 点钟方向，270° = 9 点钟方向。

#### radar（雷达图）

> **系列约束：**同一图表中允许多个 radar 系列（共用一组辐射轴），但所有系列都必须为 `radar` 类型；不得与其他类型共存。

```ts
interface RadarSeries extends LinearSeriesBase {
  type: "radar";
  encode: { category: string; y: string };    // required; the category column holds the spoke labels
  name?: string;                       // default: the encode.y column name
  areaColor?: Color | GradientFill;    // default: derived from lineColor as semi-transparent; polygon fill color
  dataLabels?: DataLabelConfig;        // default: not shown; content only takes "value"
}
```

> 雷达图的辐射轴线、蜘蛛网格和值域（最小/最大值）由图表顶层 [spokeAxis](#spokeaxisconfig辐射轴配置) 统一配置，供多个系列共享。
>
> **维度列共享约束：**同一图表中的所有雷达系列必须引用相同的 `category` 列（即所有多边形共用同一组辐射轴标签）。若要显示辐射轴标签不同的雷达图，请使用多个图表元素。校验器会检查所有 radar 系列的 `encode.category` 是否一致。

#### waterfall（瀑布图）

> **系列约束：**`series` 数组只能有 1 个元素，且不得与其他类型共存。

```ts
interface WaterfallSeries {
  type: "waterfall";
  encode: {
    x: string;                         // category column
    y: string;                         // value column (floating bars hold the increase/decrease amounts; total columns hold the absolute value of the cumulative total)
    isTotal?: string;                  // default: omitted = all floating bars; after specifying a bool column, true = total column (opening/subtotal/closing), false/null = floating bar
  };
  totalBars?:    { fill?: Color; border?: Border };   // total column (opening/subtotal/closing, isTotal=true) style
  increaseBars?: { fill?: Color; border?: Border };   // floating increase bar (y > 0) style
  decreaseBars?: { fill?: Color; border?: Border };   // floating decrease bar (y < 0) style
  dataLabels?: DataLabelConfig;        // default: not shown; content takes "value" | "category", default "value"
}
```

> **颜色：**waterfall 不使用 `fill`；颜色根据 `isTotal` 和 y 的正负映射到 `totalBars` / `increaseBars` / `decreaseBars` 三类；所有总计柱（起始/小计/结束）共用 `totalBars`。
>
> **isTotal 语义：**可出现在任意位置（首行/中间小计/末行均合法）；每个 `isTotal=true` 都是独立的总计柱，其 y 值应等于“上一总计柱的 y + 所有中间浮动柱 y 值之和”。ansatz-slide 校验器会拒绝不匹配的情况。`isTotal` 列只接受 bool 或 null；字符串 `"true"` 和数字 `1` 均无效。

#### heatmap（热力图）

Python 校验器会拒绝此类型。请在外部制作该可视化，再作为图片放置。

#### treemap（矩形树图）

Python 校验器会拒绝此类型。请在外部制作该可视化，再作为图片放置。

#### sunburst（旭日图）

Python 校验器会拒绝此类型。请在外部制作该可视化，再作为图片放置。

#### sankey（桑基图）

Python 校验器会拒绝此类型。请在外部制作该可视化，再作为图片放置。

#### 字段速查

##### 5.1 数据编码通道

| 类型 | 编码通道 |
|---|---|
| bar / line / area | `x` + `y` |
| scatter | `x` + `y`（多系列使用宽表并以 null 补齐） |
| bubble | `x` + `y` + `size`（多系列使用宽表并以 null 补齐） |
| pie | `category` + `value` |
| radar | `category` + `y` |
| waterfall | `x` + `y` + 可选的 `isTotal`（bool 列） |

> **命名约定：**笛卡尔图使用 `x` / `y`；pie 和 radar 使用 `category`。

##### 5.2 颜色机制

| 类型 | 颜色字段 | 说明 |
|---|---|---|
| bar | `series[].fill` | 柱体填充色 |
| line | `series[].lineColor` | 线条颜色（无面积） |
| area | `series[].lineColor` + `series[].areaColor` | 描边色 + 区域色（省略区域色时，会从 lineColor 派生为半透明色） |
| radar | `series[].lineColor` + `series[].areaColor` | 多边形描边 + 填充（同 area） |
| scatter | `series[].fill` / `marker.fill` | 系列级颜色作为标记默认色；`marker.fill` 优先 |
| bubble | `series[].fill` | 气泡填充色 |
| pie | 单个系列的 `fill` 数组，按数据点/节点循环取色 | 按数组长度循环复用 |
| waterfall | `series[].totalBars` / `increaseBars` / `decreaseBars` | 映射为三类——总计（总计柱）/ 增加 / 减少；不参与主题颜色循环 |

##### 5.3 图表顶层字段的适用范围

| 顶层字段 | 适用的系列类型 |
|---|---|
| `xAxis` | bar / line / area / scatter / bubble / waterfall |
| `yAxis` | bar / line / area / scatter / bubble / waterfall |
| `barWidth` / `barGap` | bar / waterfall（柱形布局参数） |
| `categoryGap` | bar / waterfall（类别间距参数） |
| `spokeAxis` | radar（包括辐射轴线 + 蜘蛛网格 + 最小/最大值） |
| `legend` | bar / line / area / scatter / bubble / pie / radar / waterfall |
| `title` | 全部 |
| `dataLabels` | 支持的系列 |
| `fontFamily` | 全部 |

> **坐标轴单值与数组规则：**次坐标轴始终位于**数值轴所在的一侧**——纵向图使用 `yAxis` 数组 + `yAxisIndex`，横向图使用 `xAxis` 数组 + `xAxisIndex`。任何系列使用 `xAxisIndex > 0` / `yAxisIndex > 0` 时，对应的 `xAxis` / `yAxis` 都必须是数组（长度 ≥ 最大索引 + 1）。

##### 5.4 类型混用兼容性速查

```
bar / line / area / scatter / bubble may coexist with each other freely
```

其余 7 种类型均独占 series 数组；详细约束见对应章节首行。

##### 5.5 dataLabels.content 值速查

| 类型 | 允许的值 | 默认值 |
|---|---|---|
| bar / line / area / scatter / bubble / radar | `value` | `value` |
| pie | `value` / `percentage` / `category` | `value` |
| waterfall | `value` / `category` | `value` |

> 受支持的图表类型应使用此处列出的标签模式。

---

#### 示例

**柱形图（堆叠）**

```yaml
- elementId: c1
  elementType: chart
  bounds: [50, 100, 600, 400]
  data:
    cols: [quarter, revenue, cost]
    rows:
      - [Q1, 120, 220]
      - [Q2, 132, 182]
      - [Q3, 101, 191]
      - [Q4, 134, 234]
  seriesDefaults:
    bar: {stack: value}
  series:
    - type: bar
      encode: {x: quarter, y: revenue}
      name: Revenue
      fill: "$primary"
    - type: bar
      encode: {x: quarter, y: cost}
      name: Expenses
      fill: "$accent"
```

**折线图（多系列区分）**

```yaml
- elementId: c2
  elementType: chart
  bounds: [50, 100, 600, 400]
  data:
    cols: [month, actual, target, baseline]
    rows:
      - [Jan, 72, 65, 50]
      - [Feb, 85, 70, 50]
      - [Mar, null, 78, 50]
      - [Apr, 90, 82, 50]
  yAxis: {min: 0, max: 100, gridLine: {color: "#f0f0f0"}}
  series:
    - type: line
      encode: {x: month, y: actual}
      name: Actual
      lineColor: "#5470c6"
      lineStyle: solid
      width: 3
      smooth: true
    - type: line
      encode: {x: month, y: target}
      name: Target
      lineColor: "#ee6666"
      lineStyle: dash
      smooth: true
    - type: line
      encode: {x: month, y: baseline}
      name: Baseline
      lineColor: "#999999"
      lineStyle: dot
      width: 1
      marker: false
```

**面积图（河流式堆叠）**

```yaml
- elementId: c3
  elementType: chart
  bounds: [50, 80, 700, 400]
  title: Traffic Evolution by Channel
  data:
    cols: [week, web, app, partner]
    rows:
      - [W1, 200, 120, 80]
      - [W2, 240, 160, 90]
      - [W3, 260, 200, 110]
      - [W4, 280, 240, 130]
  seriesDefaults:
    area: {stack: stream}
  series:
    - type: area
      encode: {x: week, y: web}
      name: Web
      areaColor: "#5470c6"
    - type: area
      encode: {x: week, y: app}
      name: App
      areaColor: "#91cc75"
    - type: area
      encode: {x: week, y: partner}
      name: Partner
      areaColor: "#fac858"
```

**气泡图（多系列分组）**

```yaml
- elementId: c5
  elementType: chart
  bounds: [50, 80, 700, 420]
  title: User Distribution
  xAxis: {title: Age}
  yAxis: {title: "Annual income (10K)"}
  data:
    cols: [age_s, inc_s, pop_s, age_w, inc_w, pop_w, age_m, inc_m, pop_m]
    rows:
      - [22, 5, 120, 28, 12, 380, 45, 40, 180]
      - [null, null, null, 35, 25, 260, 52, 60, 90]
  seriesDefaults:
    bubble:
      sizeScale: sqrt
      sizeRange: [8, 48]
  series:
    - type: bubble
      encode: {x: age_s, y: inc_s, size: pop_s}
      name: Students
      fill: "#5470c6"
    - type: bubble
      encode: {x: age_w, y: inc_w, size: pop_w}
      name: White-collar
      fill: "#91cc75"
    - type: bubble
      encode: {x: age_m, y: inc_m, size: pop_m}
      name: Management
      fill: "#ee6666"
```



**瀑布图**

```yaml
- elementId: c9
  elementType: chart
  bounds: [50, 80, 700, 380]
  title: Cash Flow Waterfall
  data:
    cols: [phase, amount, total]
    rows:
      - [Opening balance, 500, true]
      - [Sales revenue, 300, null]
      - [Operating expenses, -180, null]
      - [Taxes, -60, null]
      - [Closing balance, 560, true]
  series:
    - type: waterfall
      encode: {x: phase, y: amount, isTotal: total}
      totalBars: {fill: "#5470c6"}
      increaseBars: {fill: "#91cc75"}
      decreaseBars: {fill: "#ee6666"}
      dataLabels: {show: true}
```







**seriesDefaults 与混用：柱形默认宽度 + 折线默认平滑**

```yaml
- elementId: c15
  elementType: chart
  bounds: [50, 80, 700, 420]
  data:
    cols: [month, sales, growth]
    rows:
      - [Jan, 120, 0.10]
      - [Feb, 150, 0.25]
      - [Mar, 180, 0.20]
  yAxis:
    - {title: Sales}
    - {title: Growth rate, label: {numberFormat: "0%"}}
  seriesDefaults:
    bar:
      fill: "#5470c6"
    line:
      smooth: true
      width: 2
      lineColor: "#ee6666"
  barWidth: 0.6
  series:
    - type: bar
      encode: {x: month, y: sales}
      name: Sales
    - type: line
      encode: {x: month, y: growth}
      name: Growth rate
      yAxisIndex: 1
```

**横向柱形图（类别轴位于 y 侧）**

```yaml
- elementId: c16
  elementType: chart
  bounds: [50, 80, 600, 360]
  title: Headcount by Department
  data:
    cols: [dept, headcount]
    rows:
      - [Engineering, 120]
      - [Product, 45]
      - [Design, 30]
      - [Operations, 60]
  xAxis: {label: {numberFormat: "#,##0"}}
  yAxis: {label: {fontSize: 12}}
  series:
    - type: bar
      encode: {x: headcount, y: dept}
      fill: "$primary"
      dataLabels: {show: true}
```

---

## 6. 动画

可选的 `animations` 数组用于编排当前页面上各元素的动画。`animations` 是页面级字段，通过 `elementId` 引用页面 `elements` 数组中的元素。数组顺序决定动画之间的先后关系，`trigger` 决定每个动画何时开始。

> **验证边界：**本地回归测试可证明目标 ID、效果节点、时长、根级切换顺序和 timing XML 序列化结果。静态幻灯片渲染只能显示合成后的版面，无法证明动画播放效果。若要声称触发方式/时序一致，必须在指定的 PowerPoint、WPS 或 Keynote 中实际播放幻灯片并观察。

```ts
type AnimationEffect =
  | "appear" | "fade-in" | "fly-in" | "zoom-in" | "wipe-in" | "float-in" | "peek-in" | "rise-in"
  | "pulse" | "grow-shrink" | "spin" | "teeter" | "fill-color" | "transparency" | "color-pulse"
  | "disappear" | "fade-out" | "fly-out" | "zoom-out" | "wipe-out" | "float-out"
  | "motion-path";

type AnimationTrigger = "onClick" | "withPrevious" | "afterPrevious";
type AnimationDirection = "up" | "down" | "left" | "right";
type AnimationEasing = "linear" | "ease-in" | "ease-out" | "ease-in-out";

interface Animation {
  elementId: string;                 // required; must reference an existing element on this page
  effect: AnimationEffect;           // required; animation effect
  trigger?: AnimationTrigger;        // default: "onClick"
  direction?: AnimationDirection;    // default: "up"; only used by fly/wipe/peek/float effects
  durationMs?: number;               // default: the default duration of the corresponding effect; constraint: > 0
  delayMs?: number;                  // default: 0; constraint: >= 0
  easing?: AnimationEasing;          // default: "linear"
  repeat?: number;                   // default: 1; constraint: positive integer
  path?: string;                     // required when using motion-path
  color?: string;                    // required for fill-color / color-pulse; 6-digit HEX, with optional #
  amount?: number;                   // required for transparency; target opacity; constraint: [0, 1]
}
```

**示例：**

```yaml
elements:
  - elementId: title
    elementType: text
    bounds: [60, 40, 600, 60]
    content: {fontSize: 40, text: Title}
  - elementId: photo
    elementType: image
    bounds: [60, 140, 400, 300]
    src: media/pic.png
animations:
  - elementId: title
    effect: fade-in
    trigger: onClick
  - elementId: photo
    effect: fly-in
    direction: up
    trigger: withPrevious
  - elementId: photo
    effect: pulse
    trigger: afterPrevious
```

### 效果

- 入场：`appear` 立即出现，`fade-in` 淡入，`fly-in` 飞入，`zoom-in` 缩放进入，`wipe-in` 擦入，`float-in` 淡入并轻微漂移（约页面高度的 10%，幅度小于 `fly-in`），`peek-in` 从元素自身边缘遮罩后滑出且不淡入，`rise-in` 从页面下方线性上升且不淡入
- 强调：`pulse` 脉冲（放大到 110% 后恢复），`grow-shrink` 放大到 150%，`spin` 旋转 360°，`teeter` 左右摇摆，`fill-color` 改变填充色并保留结果，`transparency` 改变不透明度并保留结果，`color-pulse` 改变填充色后恢复原色
- 退场：`disappear` 立即消失，`fade-out` 淡出，`fly-out` 飞出，`zoom-out` 缩小退出，`wipe-out` 擦除退出，`float-out` 淡出并轻微漂移
- 路径：`motion-path` 沿路径移动

| 效果 | 默认时长 |
|---|---|
| `fade-in`, `fade-out`, `fly-in`, `fly-out`, `zoom-in`, `zoom-out`, `wipe-in`, `wipe-out`, `float-in`, `float-out`, `peek-in` | 500ms |
| `pulse` | 600ms |
| `grow-shrink`, `spin`, `fill-color`, `transparency`, `color-pulse` | 2000ms |
| `teeter`, `rise-in` | 1000ms |
| `motion-path` | 2000ms |
| `appear`、`disappear` | 瞬时；忽略 `durationMs` |

### 参数化强调效果

| 效果 | 参数 | 视觉行为 |
|---|---|---|
| `fill-color` | `color`，必需 | 将填充色从当前颜色过渡到 `color`，动画结束后保留目标颜色 |
| `transparency` | `amount`，必需 | 将不透明度从当前值过渡到 `amount`，动画结束后保留目标不透明度；`0` 完全透明，`1` 完全不透明 |
| `color-pulse` | `color`，必需 | 将填充色过渡到 `color`，然后恢复原色，不保留中间状态 |

```yaml
animations:
  # Highlight a process step: change the fill to amber and preserve it
  - elementId: step-2
    effect: fill-color
    color: "#F59E0B"
    trigger: onClick

  # Dim a secondary element: reduce its opacity to 30%
  - elementId: bg-decoration
    effect: transparency
    amount: 0.3
    trigger: withPrevious

  # Emphasize the current card: pulse red once, then restore the original color
  - elementId: card-current
    effect: color-pulse
    color: "#EF4444"
    trigger: afterPrevious

  # Bring body text in gently
  - elementId: body-text
    effect: float-in
    direction: up
    easing: ease-out
```

### 触发方式与分组

- `onClick` 开始一个新的单击组，并在单击时播放
- `withPrevious` 与前一个动画同时开始
- `afterPrevious` 在前一个动画结束后自动开始
- 若页面上的首个动画使用 `withPrevious` 或 `afterPrevious`，则以它开头的组会在进入页面时自动播放
- 若要让多个元素在单击后同时进入，将第一个动画设为 `onClick`，其余设为 `withPrevious`
- 需要按顺序播放的动画使用 `afterPrevious`

### direction（方向）

`direction` 表示移动方向或擦除推进方向。对于入场效果，`up` 表示从页面下方向上进入；对于退场效果，`up` 表示向页面上方离开。此字段只影响 fly/wipe/peek/float 效果，其他效果会忽略它。float 效果只支持 `up` 和 `down`；`rise-in` 不使用此字段，始终从页面下方向上升起。

### motion-path（运动路径）

`path` 是 SVG 路径字符串。路径坐标是相对于元素当前位置的偏移量，以页面 px 为单位。路径必须以 `M 0 0` 开始，且只能包含一个子路径；后续支持 `L`（直线）、`Q` / `C`（曲线），不支持 `Z` 闭合及其他路径命令。例如，`M 0 0 L 200 -100` 会使元素向右移动 200px、向上移动 100px。

同一元素可以按数组顺序定义多个动画。是否使用动画由用户要求及[风格规范](style.md)决定。

## 强制几何检查与有意叠放

页面对象可以选择设置 `allowedOverlaps`，即对象列表；每个对象包含
`elements: [firstElementId, secondElementId]` 和非空的 `reason` 字符串。ID
必须互不相同、存在于该页面中，且每对条目唯一。此元数据
不会改变 OOXML；它只记录针对该元素对的作者意图。

导出和源文件发布会拒绝未声明的正面积边界重叠，以及画布外的元素。
边界框会对旋转采取保守估算；页面背景与元素分开处理。诊断信息、
草稿清单发布和修复流程见[强制几何检查关卡](production/cli.md)。
