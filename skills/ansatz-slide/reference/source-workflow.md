# From source material to PPTX

## File roles

The user may supply text, images, descriptions, and data. An agent prepares the
content and layout; the Python exporter reads a structured project. It does not
call an LLM, infer a narrative, or turn raw CSV data into plots automatically.

```text
project/
  pptx.yaml             # required manifest: version, size, ordered page paths
  pages/
    01.page.yaml             # one page: text, objects, bounds, styles, image references
    02.page.yaml
  media/                 # referenced images/figures, when used
  result.pptx            # generated OOXML ZIP package
```

`pptx.yaml` and page files are ordinary UTF-8 YAML text. The manifest records presentation settings and page references. JSON syntax is also
accepted inside these YAML files. Manifests must be named `pptx.yaml` or
`<name>.pptx.yaml`; page files must end in `.page.yaml`.
Set the schema version to `version: v2`.

`input/`, `working/`, plotting scripts, and source notes may help organize a task,
but are not mandatory compiler inputs. Deliver the manifest, every referenced
page, and all local assets together. Paths are relative to the manifest's
parent directory, including image paths written inside page files.

## Preparation and export

1. Extract usable text/data from supplied documents, preserving sources and
   qualifications. Descriptions guide the agent's authoring decisions.
2. Retain supplied images or use dedicated tools to produce figures/tables.
   A plotting script may read CSV and write `media/figure.png`; the exporter
   reads the resulting image, not the CSV. Native chart/table fields are a
   separate supported compatibility path and require explicit structured data.
3. Write the manifest and page YAML using [the executable starter](authoring-start.md).
   The manifest references the page files; a page is not compiled into another
   manifest. Assets are referenced rather than embedded as arbitrary binary YAML.
4. Validate and export using [operations](operations.md). `project.load_project`
   reads the manifest and pages, validates them, and assembles an in-memory
   object. No extra merged JSON file is required. Assets are resolved and the
   Python writer produces XML parts, relationships, and media inside `.pptx`.
5. Inspect the actual output and review its appearance in the target consumer
   using [delivery checks](delivery-checks.md).

## Syntax layers

YAML is the text container. The source schema defines manifest, page and element fields.
Rich text accepts a documented HTML subset; equations accept a limited TeX subset
and export Office Math. SVG assets/path fields are separate vector inputs. Style
Markdown and TypeScript-shaped reference examples explain authoring; the exporter
does not execute them. Consult [the field reference](presentation-schema.md) only as needed.

## Discovery and preview

Pass `pptx.yaml` explicitly, or a directory containing one manifest at its root.
Only `pptx.yaml` / `*.pptx.yaml` are manifest candidates. Pages and unrelated
configuration are ignored by name; malformed manifests still produce errors.
Multiple manifests require an explicit path. Page files can be nested; discovery
does not recursively search subprojects.

For a standalone one-slide PPTX, write a manifest whose `pages` list contains
only the selected `.page.yaml` and export normally. A page alone has no global
canvas/theme context and is not a direct CLI input. To replace a page in an
existing presentation, use `replace-page`; this exports a full candidate before
transplanting the selected page. Only supported schema elements are controllable;
this is not a promise of every PowerPoint feature.

Review final output with the intended consumer
(for example PowerPoint, WPS, or LibreOffice); report which one was used.
Academic decks normally omit element animations; use `--transition none` when
slide transitions are also unwanted.
