# Commands and environment

Use actual paths from the current installation; examples below contain placeholders, not directories to assume exist. Core commands require Node 24+ and the packaged YAML dependency/WASM. An installed local exporter does not require Python, npm or a browser to run.

## Core validation and export

From a source checkout or installed npm package root:

```bash
node bin/ansatz-slide.js validate /absolute/project/deck.pptd
node bin/ansatz-slide.js export /absolute/project/deck.pptd -o /absolute/project/result.pptx
```

From any working directory, when only an installed skill directory is available:

```bash
node /absolute/skill/scripts/local-export/export-pptd.mjs /absolute/project/deck.pptd --validate-only
node /absolute/skill/scripts/local-export/export-pptd.mjs /absolute/project/deck.pptd -o /absolute/project/result.pptx
```

The public package also exposes `npx ansatz-slide validate`, `export`, `incremental` and `serve`. Prefer an already installed runtime; do not introduce an implicit download when the local command works. A directory may replace the manifest argument only when it contains exactly one `.pptd` file.

Export is local by default; `--no-sign` is a compatibility no-op. Remote images referenced by the project may still require network access. The core exporter overwrites the explicitly named output: choose a new path when replacing an existing deliverable has not been authorized. `--transition none` disables the default fade transition. Do not use `--embed-fonts` as a delivery solution: this path does not supply font payloads.

## Optional tools

| Operation | Additional requirement | Missing requirement |
| --- | --- | --- |
| Incremental PPTX replacement | Python 3.11+, standard library | Preserve baseline; report blocker, do not substitute a full overwrite |
| Browser editing | Existing Chrome/Chromium/Edge for writable folder access | Read-only upload may work; do not claim changes were saved |
| Browser preview export | Locked Python QA extras, local agent-browser, existing system browser | Skip optional preview or report blocker; core export remains available |
| Final visual review | Office-compatible renderer and a visual reviewer | Deliver with final visual QA explicitly unverified |

For browser preview, locate the skill and use its `scripts/export_images.py --help`. Run it via `uv run --project /absolute/skill --frozen --extra qa python ...`. Set a permitted local `UV_CACHE_DIR`; put the locally installed `node_modules/.bin` on `PATH`. The supported optional browser driver is `agent-browser@0.34.0`, installed locally with `npm install --no-save --package-lock=false agent-browser@0.34.0` only when needed and authorized. Never download Chromium automatically.

To edit manually, run `node bin/ansatz-slide.js serve` from the package root, or use the available public CLI. Open the printed loopback URL and authorize the project directory. The HTTP service serves static assets; writable saving uses browser directory handles, not an HTTP file-write API.

For source development, dependency versions live in `package-lock.json` and `uv.lock`. Use `npm ci` and the frozen Python environment rather than global installs. Use the workspace's permitted scratch location for logs, caches and renders; do not override its temporary-file policy.
