# Commands and environment

Use Python 3.11+ with PyYAML 6.0.3 in a local environment. JSON syntax inside the supported source filenames can also be read with the standard library alone.

## Checkout

Run from the repository root:

```bash
mkdir -p tmp/uv-cache tmp/test-tmp
export UV_CACHE_DIR="$PWD/tmp/uv-cache"
export TMPDIR="$PWD/tmp/test-tmp"
uv sync --frozen
uv run --frozen ansatz-slide validate ./deck/pptx.yaml
uv run --frozen ansatz-slide export ./deck/pptx.yaml -o ./result.pptx --offline
uv run --frozen ansatz-slide inspect ./result.pptx
```

Replace `./deck/pptx.yaml` with the actual project. An existing Python environment with the dependencies can use `PYTHONPATH=src python3 -m ansatz_slide` instead of `uv run --frozen ansatz-slide`.

## Standalone Skill

Install into an Agent's skills parent directory:

```bash
uv run --frozen ansatz-slide install-skill --target ./tmp/skills
```

The installed directory contains instructions, `python/ansatz_slide`, scripts, templates and a locked Python environment definition. In that directory:

```bash
UV_CACHE_DIR="$PWD/tmp/uv-cache" uv sync --frozen
uv run --frozen python scripts/ansatz_slide.py validate /absolute/project/pptx.yaml
uv run --frozen python scripts/ansatz_slide.py export /absolute/project/pptx.yaml -o /absolute/result.pptx --offline
```

Use the actual skills parent directory as `--target`. Replacing an existing installation requires `--force`; do so only within the user's authorization. Install dependencies in the local environment.

## Source and output rules

See [source workflow](source-workflow.md) for the project layout. A directory input must contain exactly one `pptx.yaml` or `*.pptx.yaml` manifest at its root. Pages use `*.page.yaml`.

Validation rejects unknown fields, unsupported chart types, invalid references, malformed rich text and table merges. Asset loading also checks availability and path containment during export; a successful `validate` is not a substitute for exporting the actual assets. YAML duplicate keys, recursive aliases, merge keys and language-specific object tags are rejected. Mapping keys must be strings. Unquoted `on`, `off`, `yes` and `no` remain text.

Export validates before writing and uses atomic output replacement. An existing output requires `--force`; source files and referenced assets cannot be used as output. `--offline` rejects remote images; otherwise explicitly referenced HTTP/HTTPS images can be fetched with a timeout. Local assets must remain inside the project.

The default slide transition is fade; `--transition none` disables it. Element animation is configured in page objects. Fonts are not embedded.

## Page replacement

```bash
uv run --frozen ansatz-slide replace-page --baseline ./baseline.pptx \
  --project ./edited-deck --page 2 -o ./updated.pptx --offline --transition none
```

Pages are one-based. This exports a full candidate and transplants the selected page with its dependencies. Follow [page-edit](page-edit.md) for source-scope and preservation checks; retain the baseline when replacement fails.

## Review and development

`inspect` checks the actual ZIP/XML structure, relationships and page count. Review the final PPTX in the intended presentation application for layout and fonts; observe slideshow playback to verify animations. State which application was used.

From a checkout, run the complete suite with:

```bash
TMPDIR="$PWD/tmp/test-tmp" UV_CACHE_DIR="$PWD/tmp/uv-cache" \
  uv run --frozen python -m unittest discover -v
```

Tests include recorded-output regressions. Keep scratch files and logs in `tmp/`. Tests are maintained in the source repository, not the installed Skill.
