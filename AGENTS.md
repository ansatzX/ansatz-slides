# 项目使用约定（AGENTS.md）

本文件记录 `ansatz-slide` 仓库的工作约定，供所有 Agent 会话遵循。

## 仓库边界

- 仓库根目录固定为 `/Users/ansatz/data/code/ansatz-slide`。
- `.scripts/` 与 `.state-machine/` 是其他 Agent/Skill 产生的本地工作状态，不属于 `ansatz-slide` 功能包，不得提交或发布。
- `docs/NEXT_RUN.md` 是仓库内部交接文档，可以保留在源码仓库，但不得进入 npm 包。
- 不复制或提交旧仓库的 `.git/`、`node_modules/`、`.venv/`、`tmp/`、缓存和打包产物。
- 先确认当前目录和 Git 状态；如果会话仍位于旧工作区，不得把旧副本当作主仓库。新仓库写入不在当前沙箱权限内时，按宿主权限流程申请，不绕过限制。
- 保留已有未提交修改，不擅自重置、覆盖或提交其他会话的工作。

## 当前维护目标与非目标

- 目标是让技能包指令明确、无冲突、可执行；不以跨模型能力评测作为完成条件，不主动启动模型对照实验。
- 本项目以 PPTD → PPTX 为主，不承诺任意 PPTX 无损反向转换，也不把浏览器作为核心导出的必需依赖。
- 当前优化限于一方代码、文档和流程。未经单独批准，不修改 WASM、第三方编译资源、内部协议命名空间或版权声明。
- 对外统一使用 `ansatz-slide`；不重新引入旧品牌、远程登录或签名入口。保留的第三方内部标识属于兼容边界，不对其做全局字符串替换，也不宣称全仓库已零残留。
- 根目录维护一个 README，不新增中英双版；详细操作放入对应参考文档，避免复制多套流程。

## 指令维护方式

- `skills/ansatz-slide/SKILL.md` 只保留任务入口、关键约束和按需路由；不以固定行数为目标，也不要求每个任务读取整份 DSL 或全部风格。
- `reference/agent-contract.md`：事实、权限、视觉规则的优先级与失败处理。
- `reference/authoring-start.md`：经过真实导出测试的最小 DSL；`reference/pptd.md`：按字段查阅的完整格式与兼容边界。
- `reference/operations.md`、`reference/page-edit.md`、`reference/delivery-checks.md` 分别维护命令环境、单页修改与交付验收。修改行为时同步对应说明和测试，避免多处定义互相漂移。
- 方法论、视觉体系和可执行语法分开写。场景/风格中的密度、配色、卡片和留白规则是视觉默认值，不得覆盖用户模板、事实、可读性或严格校验。
- 只加载当前任务需要的场景/风格。同名风格按 inventory 选择主定义；备选仅按明确路径使用，不混合套用。
- 写清输入、动作、产物、失败条件和完成证据；区分必须约束、默认建议和可选步骤。避免主观质量口号、机械措辞禁令和隐含工具假设。

## 临时文件：只用 ./tmp，禁用系统 /tmp

- 禁止使用系统 `/tmp` 目录存放任何测试产物或中间文件。
- 测试、脚手架、中间产物和报告统一放在仓库根目录的 `./tmp/`。
- `./tmp/` 已加入 `.gitignore`；不要在未获清理授权时删除需交接的证据或归档。重要的长期回归材料应进入正式测试目录，不让文档依赖临时报告。

## 依赖安装：只装本目录，禁止全局安装

- 禁止使用 `npm install -g`，也不得把 Python 包安装到系统或用户环境。
- Node 要求 24+；运行依赖使用仓库的 `package-lock.json`，优先执行 `npm ci`。npm 缓存使用 `./tmp/npm-cache`。
- Python/QA 依赖使用 `uv.lock`，命令应带 `uv run --frozen`；缓存放在 `./tmp/uv-cache`。
- `agent-browser` 是可选浏览器预览工具，不是核心导出依赖。需要且获准安装时，先检查 `node_modules/.bin/agent-browser`；缺少时执行：

```bash
npm install --no-save --package-lock=false agent-browser@0.34.0
```

- 不得自动下载 Chromium；优先复用系统已有 Chrome、Chromium 或 Edge。

## 导出与质检命令

优先使用仓库本地 CLI，避免隐式下载：

```bash
node bin/ansatz-slide.js validate /absolute/project/deck.pptd
node bin/ansatz-slide.js export /absolute/project/deck.pptd -o /absolute/project/result.pptx
```

直接 Node 导出和公共 CLI 均默认离线；`--no-sign` 仅为兼容参数。远程素材仍可能联网读取。核心路径不嵌入字体，不能把字体名称或浏览器可显示等同于交付机器已安装字体。

`export_pptx.py` / `export_images.py` 优先查找仓库本地 `node_modules/.bin/agent-browser`，
也可通过 `ANSATZ_SLIDE_AGENT_BROWSER` 显式指定。调用兼容 Python 脚本时使用本地 PATH：

```bash
PATH="$PWD/node_modules/.bin:$PATH" UV_CACHE_DIR="$PWD/tmp/uv-cache" \
  uv run --frozen python skills/ansatz-slide/scripts/export_pptx.py <deck> ...
PATH="$PWD/node_modules/.bin:$PATH" UV_CACHE_DIR="$PWD/tmp/uv-cache" \
  uv run --frozen --extra qa python skills/ansatz-slide/scripts/export_images.py <deck> ...
```

缺少依赖时应明确失败并给出本地安装命令，不得回退到 `pip --user`、`npm -g` 或自动安装浏览器。

## 追根问底：以代码和实测为准，不采信 md

- `SKILL.md`、`pptd.md` 和 README 中包含上游格式说明；它们不能替代本地实现验证。
- 严格校验器必须在写文件前拒绝已知无法保持语义的 DSL；不得为兼容旧示例恢复静默降级。
- 下结论前检查实际 WASM/JS/Python 代码，并通过真实导出、PPTX 解包和 OOXML 检查验证。
- 修改单页时必须验证非目标页面的 OOXML 语义保持，不以整个 ZIP 的字节一致作为要求。
- 图、复杂图表和成品表格由外部工具或用户提供；PPTD/PPTX 负责排版、标题、标注和来源，不默认承担绘图。
- 从已有 PPTX 获取素材时检查 ZIP 内的媒体和关系，不以整页截图冒充重建后的可编辑页面。缺失证据使用明确占位，生成示意图不能冒充真实实验结果。
- 示例必须保留可执行源、资产/数据来源、真实 PPTX 和验证记录；旧主题参考缩略图不作为当前导出能力的证据。

## 单页修改与交付证据

- 修改目标 `.page` 和专属素材前后，核对非目标源文件、manifest 与共享素材哈希。需要改变共享内容时先扩展用户授权。
- 使用增量替换生成新输出，保留基准 PPTX。当前实现先导出完整候选，再移植目标页依赖；不得称为“只编译目标页”。
- 校验失败或非目标语义不一致时，不得偷偷全量覆盖作为替代成功。
- 浏览器预览只用于制作辅助。最终视觉验收检查实际导出/合并后的 PPTX，逐页看渲染结果；联系图不能代替单页细查。
- 分开报告 DSL 校验、ZIP/OOXML 检查、最终视觉检查和单页保护结果。工具不足时标记未验证或阻塞；文件存在不等于视觉通过，静态图片不证明动画播放一致。

## 改动与验证

- 修改非 `./tmp/`、`AGENTS.md` 之外的仓库文件前，先征得用户同意。
- 在用户已批准的范围内推进；大范围重组、二进制改造或扩大任务范围前再次说明并询问。工作到阶段节点应汇报，不只在结束时总结。
- 功能改动后至少运行：

```bash
mkdir -p tmp/test-tmp tmp/uv-cache tmp/npm-cache
TMPDIR="$PWD/tmp/test-tmp" npm test
TMPDIR="$PWD/tmp/test-tmp" UV_CACHE_DIR="$PWD/tmp/uv-cache" \
  uv run --frozen --extra qa python -m unittest discover -s skills/ansatz-slide/tests -v
npm_config_cache="$PWD/tmp/npm-cache" npm pack --dry-run
git diff --check
```

- 纯文档修改按风险运行相关检查：指令链接、可执行示例、Skill 格式与打包边界。若维护工具提供 Skill 校验器，定位真实路径后调用，不把某个 Agent 的本机路径写死为项目依赖。
- 不以固定测试数量作为验收目标；报告本次实际运行结果及未执行项。修改示例语法后应真实导出并检查 OOXML，不能只做文本匹配。

- 发布前确认 npm 包不包含 `docs/NEXT_RUN.md`、`.scripts/`、`.state-machine/`、`tmp/`、缓存或本机绝对路径。
- 新增运行指令必须随技能包分发，且相对引用在安装后可解析；示例画廊仍保留在源码仓库，不自动加入 npm 包。
- 不提交、不发布、不修改远端仓库，除非用户明确授权。
