# ansatz-slide 本地编辑器

仓库包含一个离线运行的 neo-ppt 兼容编辑器镜像：

- 无 iframe、无远程服务依赖、无云同步 / 分享 / 云盘 / AI
- 本地打开 PPTD 文件夹并自动保存
- 编辑器内「导出」走本地 patched WASM

## 启动

从仓库根目录启动，避免 `npx serve` 隐式下载未锁定的第三方包：

```bash
node bin/ansatz-slide.js serve
```

安装 npm 包后可用 `npx ansatz-slide serve`。浏览器打开 <http://127.0.0.1:55173/>；不要直接使用 `file://`。

## 使用

1. **打开 PPTD 文件夹**（Chromium 可读写；其它浏览器可退化为只读上传）
2. 在本地编辑器 UI 中编辑
3. 顶栏 **导出** → 下载 PPTX / 图片（无分享、无 Google 云盘）

## 结构

```
editor/
  index.html          # 唯一入口（兼容编辑器 UI + 本地顶栏）
  local-bridge.js     # 取代 Penpal 父页面的本地桥
  local-shell.css
  neo-ppt/            # 第三方兼容前端镜像
    assets/
      pptd_wasm_bg-DPPWdROu.wasm   # 唯一一份 patched PPTX WASM（真源）
      index_bg-*.wasm              # resvg（渲染用，勿与上者混淆）
```

Agent 侧 `scripts/local-export/` 在 skill install 时会从上述真源拷贝一份 `pptd_wasm_bg.wasm`；仓库内导出脚本直接引用本路径。该编辑器是手动编辑与浏览器 QA 的可选路径；核心 `validate` / `export` 不需要浏览器。
