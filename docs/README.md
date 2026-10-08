# 文档导航

文档分为三类：这里保存仓库级功能边界和开发说明；`skills/ansatz-slide/reference/` 保存随 Skill 分发的操作与内容指导；`docs/themes/` 保存[主题索引](../theme.md)引用的参考图。参考图不是当前导出的验收证据。

## 按任务阅读

| 任务 | 文档 |
| --- | --- |
| 安装并创建第一张页面 | [README](../README.md)、[最小示例](../skills/ansatz-slide/reference/authoring-start.md) |
| 环境和渲染工具 | [operations](../skills/ansatz-slide/reference/operations.md) |
| 新建、修改、拆分、合并、移动页面 | [工作对象 CLI](../skills/ansatz-slide/reference/review-cli.md) |
| 使用已有 session/token 集成 | [兼容命令](../skills/ansatz-slide/reference/review-cli-legacy.md) |
| 替换已有 PPTX 的一个页面 | [二进制单页替换](../skills/ansatz-slide/reference/page-edit.md) |
| 查询字段或支持边界 | [字段规范](../skills/ansatz-slide/reference/presentation-schema.md)、[支持矩阵](DSL_SUPPORT_MATRIX.md) |
| 学术叙述、数学表达、视觉检查 | [学术写作](../skills/ansatz-slide/reference/academic-authoring.md)、[公式](../skills/ansatz-slide/reference/equations.md)、[页面与整稿检查](../skills/ansatz-slide/reference/page-and-deck-review.md) |
| 交付验收 | [delivery checks](../skills/ansatz-slide/reference/delivery-checks.md) |

主流程是 `deck create → page open/update → deck export`。兼容命令仍可执行，但不作为新工作流入口。不要把文档示例中的 `WORK`、`ID` 和文件名当成已经存在的结果。

## 开发和验证

从仓库根目录运行；临时输出放在 `tmp/`：

```bash
mkdir -p tmp/test-tmp tmp/uv-cache
export TMPDIR="$PWD/tmp/test-tmp"
export UV_CACHE_DIR="$PWD/tmp/uv-cache"
uv run --frozen python -m unittest discover -v
uv build --out-dir tmp/dist
python3 scripts/verify_distribution.py --wheel tmp/dist/ansatz_slide-0.0.1-py3-none-any.whl --sdist tmp/dist/ansatz_slide-0.0.1.tar.gz
git diff --check
```

验证按职责区分：字段/几何、源文件事务、OOXML 差分、打包安装和真实演示软件渲染。测试代码与固定期望值是可复现证据；测试数量和一次旧运行结果不是永久通过保证。修改内容或实现后运行相关检查。

维护时将同一规则放在一个主要位置，其他入口链接过去。操作说明放在 Skill 内以随包交付；这里不复制第二套 CLI 手册。历史报告留在本地 `tmp/`，不作为新用户必须阅读的文档。
