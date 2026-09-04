# Local patched WASM PPTX exporter

- `export-pptd.mjs` — Node 24 entry with strict validation and patched WASM glue
- Patched WASM **canonical path** (repo / npm package):
  `editor/neo-ppt/assets/pptd_wasm_bg-DPPWdROu.wasm`; skill install copies it to
  `scripts/local-export/pptd_wasm_bg.wasm`.
- Used by `ansatz-slide validate`, `ansatz-slide export`, and the transitional `../export_pptx.py` wrapper

```bash
# preferred public commands
npx ansatz-slide validate /path/to/project
npx ansatz-slide export /path/to/project -o out.pptx

# direct developer command from the repository root
node skills/ansatz-slide/scripts/local-export/export-pptd.mjs \
  /path/to/project -o out.pptx --no-sign
```

Both direct and public export are offline by default; `--no-sign` is a backward-compatible no-op. Remote image URLs still require network access. It does not embed fonts. Five chart types known to lose their visual/OOXML meaning (`candlestick`, `heatmap`, `treemap`, `sunburst`, and `sankey`) are rejected before the writer runs; use an external PNG/SVG or a labeled placeholder.

This is a one-way PPTD-to-PPTX exporter. Existing PPTX files are not parsed into PPTD here. Use `ansatz-slide incremental` at the public CLI level when replacing one generated slide while preserving non-target OOXML semantics.
