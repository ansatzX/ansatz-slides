# 五种风格示范的验证记录

这不是旧 PPT 的翻版，也没有把整页截图塞回 PPTX。每个项目由新编写的内容、PPTD 页面与一张外部制图资产构成。业务数据是明确标注的示例数据；学术页使用可直接验证的解析函数，不冒充实验结果。

## 方法与复现

在仓库根目录执行（字体目录以 macOS 为例；其他系统提供包含同名 Arial 字体文件的合法目录）：

```bash
mkdir -p tmp/example-qa
UV_CACHE_DIR="$PWD/tmp/uv-cache" uv run --frozen --extra qa python \
  example/verified-styles/build.py --font-dir /System/Library/Fonts/Supplemental --export
UV_CACHE_DIR="$PWD/tmp/uv-cache" uv run --frozen --extra qa python \
  example/verified-styles/verify.py --scratch "$PWD/tmp/example-qa"
```

第一步使用 Pillow 独立生成图表/表格 PNG，再由仓库 CLI 导出 PPTX。第二步需要已安装的 LibreOffice、Poppler（`soffice`、`pdftoppm`、`pdftotext`），检查 OOXML 后从实际 PPTX 渲染预览。不安装任何浏览器，不下载字体。现有 PNG 和 PPTD 可直接导出，不需要 Pillow 或字体文件来重画图。

`build.py` 会覆盖此目录内五个项目的示范源文件和输出；自行修改示例前先复制项目。复现结果受字体与渲染器版本影响；不承诺 ZIP/PNG 字节一致。

## 结构验证

五份输出均通过严格导出、ZIP 完整性检查、元素出界检查及根级 fade 检查。每份有且仅有一张局部证据图片，其二进制与源 PNG 一致；没有原生图表或表格；标题、解释、来源保持原生文本。实际计数和产物哈希见 [verification.json](verification.json)。这些检查不等价于 Office 播放验证。

## 视觉验证：2026-09-05

检查对象为五张由 PPTX 经 LibreOffice PDF → Poppler 生成的 1440×810 预览，逐张全尺寸查看。没有用编辑器预览代替最终文件渲染。

| 风格 | 已检查内容 | 范围与适配 |
| --- | --- | --- |
| moss-green-transformation | 炭灰底、绿色就绪度条、60/40 证据与解释、底部结论；标签和文字无裁切 | 单张咨询证据页，无封面与整套章节节奏 |
| black-gold-ledger | 白底黑顶线、外部表格、对齐数字、单一金色 KPI；行合计 100/94 与 6% 差异相符 | 单张预算页，示例数据；不构成财务建议 |
| blue-flame-brand | 暗底青色柱、8 个直接标值、目标/实际口径、警示与页脚可读 | 单张趋势页；不虚构拐点原因与质量结论 |
| cream-collage | 奶油底、7 节点时间线、红蓝语义节点、留白与结论 | 单张节奏页，没有照搬旧封面或填充图片 |
| pastel-derivation | 白底、杏色解析图、蓝色公式与洋红限制、灰色结论区；上下标与符号可见 | 单张推导页，使用 Arial Unicode 文本代替上游数学字体；不宣称 LaTeX 支持 |

图与表是不可逐单元格编辑的外部 PNG，修改数据应重绘该资产；页面文字仍可编辑。采用本机已有 Arial，字体未嵌入。尚未在 PowerPoint/WPS/Keynote 中逐一复核，也未验证 60 份风格的所有页面类型；这些单页只是第一批可运行示范。

## 回归与分发检查

本次运行：Node 30/30、Python 24/24 测试通过，`git diff --check` 通过。新增测试覆盖 60 份风格的约束链接与目录、五个示范的合法 DSL/素材/原生文字、非法 scalar fit 和文字 opacity 继续被拒绝，以及示例数字勾稽。npm dry-run 为 311 个文件，约 11.1 MB；包含新的运行约束与目录，不包含示范资产、内部交接文档或本地工作状态。没有修改运行时实现或放宽校验器，也没有提交或发布。
