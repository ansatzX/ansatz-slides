# 文档导航

这里保存仓库级功能边界、开发说明与手工评测用例；`skills/ansatz-slide/reference/` 保存随 Skill 分发的操作、内容指导和唯一的[学术排版规范](../skills/ansatz-slide/reference/style.md)。Style 与内容方法分开维护。

## 按任务阅读

| 任务 | 文档 |
| --- | --- |
| 安装并创建第一张页面 | [README](../README.md)、[最小示例](../skills/ansatz-slide/reference/production.md) |
| 环境和渲染工具 | [operations](../skills/ansatz-slide/reference/production.md) |
| 新建、修改、拆分、合并、移动页面 | [工作对象 CLI](../skills/ansatz-slide/reference/production/cli.md) |
| 使用已有 session/token 集成 | [兼容命令](../skills/ansatz-slide/reference/production/cli.md#兼容命令) |
| 替换已有 PPTX 的一个页面 | [二进制单页替换](../skills/ansatz-slide/reference/production/replace-page.md) |
| 查询字段或支持边界 | [字段规范](../skills/ansatz-slide/reference/technical.md)、[支持矩阵](DSL_SUPPORT_MATRIX.md) |
| 学术叙述、数学表达、视觉检查 | [学术汇报基本方法](../skills/ansatz-slide/reference/content.md)、[公式](../skills/ansatz-slide/reference/production/equations.md)、[页面与整稿检查](../skills/ansatz-slide/reference/review.md) |
| 交付验收 | [审阅与交付](../skills/ansatz-slide/reference/review.md#交付) |

新建使用 `deck create` 或 `deck import-pages`；已有项目修改优先使用 `deck open → 编辑计划 → deck revise → review.viewer`，逐页 `page open/update` 保持兼容。兼容命令仍可执行，但不作为新工作流入口。不要把文档示例中的 `WORK`、`ID` 和文件名当成已经存在的结果。

## 开发和验证

核心代码统一在 `src/ansatz_slide/`，通用和按需加载的备注模板分别位于同一
`templates/` 根目录下的 `presentation/` 与 `notes/`；这两类目录内部保持 OOXML
包路径，不能把备注模板无条件装入没有备注的演示文稿。
自动测试与固定回归素材统一在 `tests/core/`；[学术制作手工评测用例](academic-authoring-cases.md)
由审阅者按任务使用，不随 Skill 分发，也不能代替实际页面验收。

核心模块按职责组织：`validation/` 校验共享值、内容元素、图表和整稿；
`incremental/` 分离包读取、依赖移植和对外入口；`page_api/` 分离状态、检查与发布；
`work_objects/` 分离工作谱系、候选处理和操作入口。图表公共部件在 `chart_parts.py`，
CLI 参数声明在 `cli_args.py`；提纲与论证记录统一在 `narrative.py`，检查报告在
`output.py`，包结构检查在 `package.py`，渲染与像素测量在 `rendering.py`。

Python 文件上限为 500 行，按 Ruff 格式化后的实际文件计数。行数回归覆盖核心、
入口脚本与测试；格式检查使用本机开发工具 Ruff，不增加运行时依赖。

从仓库根目录运行；临时输出放在 `tmp/`：

```bash
mkdir -p tmp/test-tmp tmp/uv-cache
export TMPDIR="$PWD/tmp/test-tmp"
export UV_CACHE_DIR="$PWD/tmp/uv-cache"
uv run --frozen python -m unittest discover -v
ruff format --check src/ansatz_slide scripts skills/ansatz-slide/scripts
uv build --out-dir tmp/dist
python3 scripts/verify_distribution.py --wheel tmp/dist/ansatz_slide-0.0.1-py3-none-any.whl --sdist tmp/dist/ansatz_slide-0.0.1.tar.gz
git diff --check
```

验证按职责区分：字段/几何、源文件事务、OOXML 差分、打包安装和真实演示软件渲染。测试代码与固定期望值是可复现证据；测试数量和一次旧运行结果不是永久通过保证。修改内容或实现后运行相关检查。

维护时将同一规则放在一个主要位置，其他入口链接过去。操作说明放在 Skill 内以随包交付；这里不复制第二套 CLI 手册。历史报告留在本地 `tmp/`，不作为新用户必须阅读的文档。

唯一风格是 Agent 的排版规范，不是 CLI 主题参数。旧设计模板及缩略图可从 Git
历史查阅；当前不维护主题 ID 或同名备选。

论文阅读须将 [read.md](../skills/ansatz-slide/reference/content/read.md) 全文加载到执行 AI 上下文，严格执行；其他任务的必读文件与附录触发条件见 [Skill 读取表](../skills/ansatz-slide/SKILL.md#按任务读取哪些文件必须读)。
