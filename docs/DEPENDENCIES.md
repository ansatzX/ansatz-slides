# ansatz-slide dependencies and distribution

This inventory describes the executable package, not aspirational documentation.

## Core runtime

| Component | Pinned requirement | Purpose | Distribution |
| --- | --- | --- | --- |
| Node.js | 24 or newer | CLI, strict validation, image resolution, WASM invocation | User/system runtime; not bundled |
| `yaml` | 2.9.0 | Parse `.pptd` and `.page` YAML | Normal npm dependency |
| patched `pptd_wasm` | bundled asset, 788,074 bytes in the current package | PPTD to PPTX writer | Shipped inside the npm tarball |
| local neo-ppt editor assets | current checked-in build | Manual editing and browser QA | Shipped inside the npm tarball |

The core `ansatz-slide validate` and `ansatz-slide export` paths use Node only. They do not need Python, a browser, login credentials, or a network request.

## Optional compatibility and QA runtime

| Component | Pinned requirement | Purpose | Distribution |
| --- | --- | --- | --- |
| Python | 3.11 or newer | Compatibility wrapper, image QA, incremental OOXML replacement | User/system runtime; not bundled; incremental path itself is standard-library only |
| PyYAML | 6.0.3 | Python compatibility wrapper | Locked by `uv.lock` |
| Pillow | 12.3.0 | Page-image inspection/contact sheets | `qa` uv extra |
| websocket-client | 1.9.2 | Browser QA control | `qa` uv extra |
| agent-browser | 0.34.0 | Drives the local editor for image QA/browser fallback | Optional local npm install with `--no-save`; not a package dependency |
| Chrome / Chromium / Edge | an already installed system browser | Browser rendering and screenshots | Never downloaded by ansatz-slide |

PowerPoint, LibreOffice, or another Office consumer is useful for independent native playback/visual verification, but is not an export dependency.

## Installation model

- Publish/distribute the core as the npm package `ansatz-slide`. A measured local package build is about 11.1 MB compressed and 21.7 MB unpacked; it contains editor/WASM assets but no Chromium binary.
- Style-reference thumbnails under `docs/themes/` and reproducible demonstrations under `example/verified-styles/` remain source-repository assets, not runtime dependencies or npm tarball contents. Adding these assets to distribution requires a separate package-size decision.
- npm installs the small `yaml` runtime dependency next to or above the package. The skill installer vendors that dependency into the copied skill so its Node scripts still run after the temporary `npx` process exits.
- The installer also copies `pyproject.toml` and `uv.lock` into the skill. Users who need Python compatibility or image QA run `uv sync --frozen` or `uv sync --frozen --extra qa` in that skill directory.
- Browser QA users install `agent-browser@0.34.0` locally in their working directory and put that local `node_modules/.bin` on `PATH`, then reuse a system Chrome-family browser. There is no Playwright/Puppeteer Chromium download.
- Global npm/pip installs and unpinned fallback installers are forbidden.

## Reproducibility boundary

- `package-lock.json` pins the Node dependency graph.
- `uv.lock` pins the optional Python dependency graph.
- The patched WASM and editor build are shipped as immutable package files.
- PPTX ZIP bytes can vary because of timestamps/compression. For single-page editing, the supported guarantee is semantic identity of non-target OOXML slide/relationship trees and their recursively associated resources, not byte-for-byte identity of the whole ZIP.
- Fonts are an external target-environment dependency unless actual embedded-font parts are verified in the output. The current core exporter does not embed them, so cross-machine/cross-consumer visual identity is not guaranteed.
- Animation timing XML and valid OOXML are structural evidence. Native playback parity and visual layout require representative tests in each promised Office consumer.
