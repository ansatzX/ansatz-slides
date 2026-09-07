# ansatz-slide

使用 Python 将 YAML 描述的演示文稿校验、导出为可编辑 PPTX、检查文件结构，并替换指定页面。Python 3.11+；JSON 输入只需标准库，常规安装包含用于 YAML 的 PyYAML 6.0.3。

## 源文件与生成流程

项目使用 `pptx.yaml` 和 `pages/01.page.yaml`：前者是全局清单，后者是页面内容，均为 YAML 文本。JSON 语法也可读取。目录输入只在项目根目录查找 `pptx.yaml` 或 `*.pptx.yaml` 清单，忽略页面及其他 YAML 配置；多个清单时必须传入具体文件路径。

文本、图片、描述、数据 → Agent 整理内容及生成图表素材 → `pptx.yaml` + `pages/*.page.yaml` + `media/` → Python 校验和导出 → `result.pptx`。导出器不直接理解自然语言或自动分析原始数据；详见[从原始材料到 PPTX](skills/ansatz-slide/reference/source-workflow.md)。

## 安装与使用

从本仓库运行，依赖只安装到项目环境：

```bash
mkdir -p tmp/uv-cache tmp/test-tmp
export UV_CACHE_DIR="$PWD/tmp/uv-cache"
uv sync --frozen
uv run --frozen ansatz-slide validate ./deck/pptx.yaml
uv run --frozen ansatz-slide export ./deck/pptx.yaml -o ./result.pptx --offline
uv run --frozen ansatz-slide inspect ./result.pptx
uv run --frozen ansatz-slide replace-page --baseline ./result.pptx --project ./edited-deck --page 2 -o ./updated.pptx --offline
```

也可将构建出的 wheel 安装到独立虚拟环境，使用同一个 `ansatz-slide` 命令。没有 uv 时，已有 Python 环境可运行 `PYTHONPATH=src python3 -m ansatz_slide`。

安装独立 Skill：

```bash
uv run --frozen ansatz-slide install-skill --target ./tmp/skills
python3 ./tmp/skills/ansatz-slide/scripts/ansatz_slide.py --help
```

将 `--target` 改成实际的 Agent skills 父目录即可安装；已有同名 Skill 时必须显式传 `--force`。安装包含指令、Python 源码和 XML 模板。依赖、完整命令与安装后运行见 [operations](skills/ansatz-slide/reference/operations.md)。

`--force` 才会覆盖已有输出；`--offline` 拒绝远程图片。流程为内容与证据 → PPTX.yaml → Python 校验及 OOXML/ZIP → 实际 PPTX → 结构检查 → 目标演示软件中的视觉验收。自动 Microsoft PowerPoint 渲染尚未接入，结构检查不证明视觉或动画播放通过。本项目不承诺任意 PPTX 无损反向转换。

## 素材原则

`ansatz-slide` 负责演示文稿的版式编排，不负责凭空制造事实素材。

- 照片、插画、复杂图表和成品表格应由用户提供，或由专门的检索、绘图和数据工具生成。
- pptx.yaml 负责素材的位置、尺寸、裁切、标题、标注和来源。
- 没有合格素材时，应保留明确标注的占位框，不得静默插入无关、错误或无法确认真实性的图片。
- 远程图片会在导出时读取；本地图片必须位于 pptx.yaml 项目目录内。缺失或读取失败会中止导出。

## 风格参考

风格选择见[主题索引](theme.md)。视觉体系与可执行语法分开维护：[运行约束](skills/ansatz-slide/reference/design-system-runtime.md) · [60 份风格文件的选择目录](skills/ansatz-slide/reference/design-system-inventory.md)。缩略图用于说明风格，不代表当前导出效果。

## 项目结构

| 目录 | 职责 |
| --- | --- |
| `src/ansatz_slide/` | 唯一 Python 实现、CLI、安装器、OOXML 模板 |
| `skills/ansatz-slide/` | Agent 指令、风格定义与独立启动脚本 |
| `tests/` | 功能、安装、Skill 合约及输出回归测试 |
| `docs/` | 支持矩阵及主题索引使用的参考图片 |

## 开发与验证

```bash
mkdir -p tmp/test-tmp tmp/uv-cache
TMPDIR="$PWD/tmp/test-tmp" UV_CACHE_DIR="$PWD/tmp/uv-cache" uv run --frozen python -m unittest discover -v
TMPDIR="$PWD/tmp/test-tmp" UV_CACHE_DIR="$PWD/tmp/uv-cache" uv build --out-dir tmp/dist
python3 scripts/verify_distribution.py --wheel tmp/dist/ansatz_slide-0.0.1-py3-none-any.whl --sdist tmp/dist/ansatz_slide-0.0.1.tar.gz
```

构建产物、缓存及临时证据只放 `tmp/`。发布包的文件范围由 `pyproject.toml` 定义，并由分发检查脚本验证。

[页面结构规范](skills/ansatz-slide/reference/presentation-schema.md) · [可执行最小示例](skills/ansatz-slide/reference/authoring-start.md) · [支持矩阵](docs/DSL_SUPPORT_MATRIX.md)

## License 与商标

本仓库代码采用 [MIT License](LICENSE)。保留原作者版权声明；第三方资源不因项目命名变化而成为本项目原创。
