# 仓库工作约定

## 项目与入口

`ansatz-slide` 是 Python 演示文稿工具，负责结构化源文件校验、PPTX 导出、结构检查和指定页面替换。Python 3.11+；依赖及构建配置以 `pyproject.toml`、`uv.lock` 为准。

每个维护中的 Python 文件不得超过 500 行（含注释和空行）。代码修改后使用 Ruff 格式化，按格式化后的实际行数检查；按职责拆分或合并，不通过压行、删除必要注释规避限制。

- `src/ansatz_slide/`：唯一核心实现；`templates/presentation/` 保存通用 OOXML 模板，`templates/notes/` 保存按需加载的备注模板。
- `validation/`、`incremental/`、`page_api/`、`work_objects/`：分别维护 DSL 校验、二进制单页移植、页面 API 与候选工作对象；包入口保留调用接口，子模块按职责划分。
- `skills/ansatz-slide/`：Agent 指令、风格定义和独立 Skill 启动脚本。
- `tests/`：功能、安装、文档示例与输出回归测试。
- `scripts/verify_distribution.py`：wheel/sdist 内容检查。
- `README.md`：安装、命令和项目说明；唯一学术风格直接见 `skills/ansatz-slide/reference/style.md`。
- `docs/README.md`：文档导航及开发验证；`docs/DSL_SUPPORT_MATRIX.md`：能力边界。

## 工作范围

操作前确认仓库路径和 Git 状态，保留用户及其他会话的未提交修改。按用户已授权范围执行；需要扩大范围时先说明原因。提交、推送和发布分别遵循用户授权，不由其中一项推定另一项。

临时文件、测试输出、缓存和构建包统一放在仓库 `tmp/`，不用系统 `/tmp`。不删除未经授权的本地资料。依赖只安装到项目环境，不进行全局或用户级安装；不提交环境、缓存、研究归档及 Agent 本地状态。

## 输入与实现边界

项目清单使用 `pptx.yaml` 或 `*.pptx.yaml`，页面使用 `*.page.yaml`。目录输入只在项目根目录寻找唯一清单；多个清单时指定文件。文件可以使用 YAML 或 JSON 语法。

标准入口为 `ansatz-slide validate/export/inspect/replace-page/page/deck/install-skill`。独立 Skill 通过 `scripts/ansatz_slide.py` 调用同一核心，不另建重复导出实现。

本地素材必须位于源项目目录内；`--offline` 拒绝远程图片。校验应在写入前拒绝无法保持语义的输入，不能静默降级。协议字段、命名空间及回归期望值不能仅为消除名称或让测试通过而替换。

## 指令与素材

只读取任务需要的内容方法、风格及操作参考。新建演示文稿默认使用唯一的 `reference/style.md`；内容方法与视觉排版分开维护，不恢复旧主题或同名备选。风格规则不能覆盖用户事实、模板、授权范围及可执行语法。

- `reference/content.md`：内容组织与讲解示例。
- `reference/style.md`：唯一视觉规范。
- `reference/production.md`：环境、源项目与最小示例；`reference/production/` 为 CLI、公式与二进制单页替换附录。
- `reference/review.md`：实际页面审阅与交付。
- `reference/technical.md`：字段与能力边界；`reference/technical/shapes.md` 为形状参数表。

上述路径均相对 `skills/ansatz-slide/`。行为修改要同步对应指令和测试，避免复制多套规则。

图表、照片和数据来自用户或适当的外部工具；导出器负责排版与标注。缺少证据时明确占位，不制造事实。参考 PPTX 用于提炼方法与排版，不能作为当前导出效果的证明。学术报告默认不加元素动画；不需要切页动画时使用 `--transition none`。

## 页面保护与验收

单页修改前后核对非目标源文件、清单及共享素材；改变共享内容须有对应授权。增量替换先生成完整候选，再移植目标页面及依赖，验证非目标页语义保持。失败时不能用全量覆盖代替成功，应保留已有交付文件。

区分源文件校验、ZIP/OOXML 检查、单页保护与最终视觉验收。最终视觉检查针对实际 PPTX，在目标演示软件中逐页进行；结构正确或图片存在不证明视觉、字体或动画播放正确。字体不嵌入，未经实际检查的部分如实说明。

## 验证命令

```bash
mkdir -p tmp/test-tmp tmp/uv-cache
export TMPDIR="$PWD/tmp/test-tmp"
export UV_CACHE_DIR="$PWD/tmp/uv-cache"
uv run --frozen python -m unittest discover -v
ruff format --check src/ansatz_slide scripts skills/ansatz-slide/scripts
git diff --check
```

标准测试发现包含记录输出的差分回归。保留独立期望值；功能变更依据预期行为检查失败原因，不从当前实现自动刷新基准。

修改打包配置或安装流程时，运行 `uv build --out-dir tmp/dist`，再用 `scripts/verify_distribution.py` 检查本次生成的 wheel 和 sdist。文档修改检查相对链接与命令是否可用。按改动风险选择检查，报告实际结果和未验证部分，不以固定测试数量作为验收目标。
