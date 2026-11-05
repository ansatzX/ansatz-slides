# ansatz-slide

用 Python 和 CLI 创建、逐页修改演示文稿源项目，导出可编辑 PPTX。模型负责内容与视觉判断，程序负责字段、几何、版本和文件写回检查。

## 安装

Python 3.11+，常规安装包含 PyYAML 6.0.3。从仓库运行：

```bash
mkdir -p tmp/uv-cache tmp/test-tmp
export UV_CACHE_DIR="$PWD/tmp/uv-cache"
export TMPDIR="$PWD/tmp/test-tmp"
uv sync --frozen
uv run --frozen ansatz-slide --help
```

也可把 wheel 安装到独立虚拟环境。安装独立 Agent Skill：

```bash
uv run --frozen ansatz-slide install-skill --target ./tmp/skills
```

系统依赖包括 **Poppler**（`pdftoppm`、`pdftotext`、`pdffonts`；公式图片另用 `pdftocairo`）。当前自动预览和文字测量还需要 **LibreOffice**，以及页面使用的字体。这些工具不由 pip/uv 安装。Deckcraft 可作为可选创建后端，也可独立渲染实际 PPTX；自动文字测量仍使用 LibreOffice/Poppler。

完整环境设置、Office 渲染依赖和独立 Skill 启动方式见[运行说明](skills/ansatz-slide/reference/production.md)。

## 创建与逐页修改

先按[可执行最小示例](skills/ansatz-slide/reference/production.md)准备 `settings.yaml` 和 `first.page.yaml`，然后运行：

```bash
uv run --frozen ansatz-slide deck create ./deck --settings ./settings.yaml --content ./first.page.yaml
uv run --frozen ansatz-slide page open ./deck --page 1
```

返回的 `work` 是后续修改引用。把修改字段写入候选文件，运行 `page update WORK --element ID --changes FILE`，或用 `--content FILE` 提供完整单页候选；`WORK` 使用上次返回的实际路径。CLI 默认返回候选、简短几何问题、相邻页逻辑和预览路径，模型需打开图片进行判断。

- 用 `deck outline` 保存每页目的、结论、证据和前后衔接。
- 用 `page insert/split/merge/move/remove` 调整局部分页和顺序。
- 几何失败后只调整布局，保留内容；连续三次失败时提示考虑拆页。
- 原生横排文本按实际字体、字号、宽度和段落设置测量，溢出阻止写回；`deck export` 同样执行文字容纳检查。
- `gates.hard` 是程序限制；`gates.live` 区分模型需遵守的语义要求和可选建议，程序不判定语义通过。

正式 YAML 由 CLI 校验后写回，首行带有通过 CLI 修改的提醒。候选可以直接编辑。清单是 `pptx.yaml` 或 `*.pptx.yaml`，引用 `*.page.yaml` 和项目内素材；页面编号由清单顺序决定。详见[工作对象命令](skills/ansatz-slide/reference/production/cli.md)。

## 导出与交付

源稿写好后先预检，处理问题再生成和渲染。`preflight` 不启动 Office、不生成 PPTX：

```bash
uv run --frozen ansatz-slide deck preflight ./deck --offline
uv run --frozen ansatz-slide deck export ./deck -o ./result.pptx --offline --transition none
uv run --frozen ansatz-slide inspect ./result.pptx
```

尚未建项目时，可用 `deck preflight ./deck --settings ./settings.yaml --plan ./pages.json`
检查待导入页面。确定错误返回非零；学术提示由 Agent 核对，`--strict` 可让提示也
返回非零。源稿检查范围与例外见[源稿预检](skills/ansatz-slide/reference/production/cli.md#源稿预检先于-pptx-与渲染)。

可选使用 `deck export ... --backend deckcraft` 从同一 YAML DSL 创建 PPTX，默认仍为 `native`。首版仅支持普通文本、基础形状和 PNG/JPEG 图片等明确子集，详见[创建后端与限制](skills/ansatz-slide/reference/production.md#可选创建后端deckcraft)。

导出会重新检查当前输入；已有输出需要 `--force`。逐页源修改不会自动更新已有完整 PPTX。若必须保留现有 PPTX 的其他页面，使用[单页替换](skills/ansatz-slide/reference/production/replace-page.md)。

交付 PPTX 以及清单、引用页面和素材。结构通过不等于字体、布局、动画或论证通过；须对照[交付检查](skills/ansatz-slide/reference/review.md#交付)说明实际验证范围。导出器不自动提炼原始材料、不嵌入字体，也不提供任意 PPTX 的无损反向转换。

## 一份计划完成多页修改与审阅

```bash
ansatz-slide deck open ./deck --page 3 --page 8 --no-preview
# 编辑返回的 plan 文件，保留 base，按页号与元素 ID 写 edits/layout。
ansatz-slide deck revise ./deck --plan /absolute/returned/plan.yaml -o ./next.pptx
```

返回一个共同版本快照和一份计划；批量检查、导出和最终渲染后再发布。失败时修正
同一计划重试，已有源和交付文件保留。旧 work 列表接口仍可使用。
`review.viewer` 提供缩略图、单页大图及问题列表，`review.manifest` 保存机器可读记录。
打开图片后用 `deck review DIRECTORY --page N --status reviewed --note TEXT` 记录观察；
视觉状态不会随导出成功自动变为通过。详见[操作参考](skills/ansatz-slide/reference/production/cli.md#项目级修改计划与统一审阅推荐)。

## 文档入口

| 目的 | 入口 |
| --- | --- |
| 文档结构、功能边界、开发验证 | [docs](docs/README.md) |
| 项目文件与运行环境 | [运行说明](skills/ansatz-slide/reference/production.md) |
| 学术报告 | [学术汇报基本方法](skills/ansatz-slide/reference/content.md) |
| 论文阅读（全文必读） | [用户完整阅读方法 read.md](skills/ansatz-slide/reference/content/read.md) |
| 字段和数据类型 | [源文件规范](skills/ansatz-slide/reference/technical.md) |
| 唯一学术风格 | [排版规范](skills/ansatz-slide/reference/style.md) |
| Agent 使用规则 | [Skill](skills/ansatz-slide/SKILL.md) |

`src/ansatz_slide/` 是唯一实现；`skills/ansatz-slide/` 是随安装分发的指令与风格；`tests/` 保存回归；`tmp/` 保存本地构建、缓存和检查结果。代码采用 [MIT License](LICENSE)，保留原作者及第三方资源归属。

The page workflow also carries a whole-deck argument (`deck brief`) and attributed, revocable user requirements/model proposals (`deck directive`). Source changes request scoped review; program measurements remain separate from semantic acceptance. See [the work-object reference](skills/ansatz-slide/reference/production/cli.md#整稿意图与有来源的要求).
