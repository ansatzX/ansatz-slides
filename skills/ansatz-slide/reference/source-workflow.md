# From supplied material to a presentation

The agent selects the narrative and prepares assets. The CLI reads structured candidates; it does not call an LLM, infer an argument or automatically plot raw data.

## File roles

```text
project/
  pptx.yaml                  # CLI-managed settings and ordered page paths
  page-<id>.page.yaml         # CLI-created page sources
  media/                     # supplied or prepared local assets
  .ansatz/                   # work revisions and model-authored outline
  .ansatz-recovery/           # retained publication recovery, when needed
```

Imported projects may use `pages/01.page.yaml` or other relative paths. Only manifest order defines page numbers. All asset paths, including those inside page sources, are relative to the manifest directory. Deliver referenced sources and assets together; runtime work/recovery data are not compiler inputs.

A manifest is `pptx.yaml` or `*.pptx.yaml`, with `version: v2`; pages end in `.page.yaml`. Directory lookup requires one manifest at its root. Explicit file lookup supports an existing multi-manifest directory, but new creation refuses to add a second manifest. Page files alone lack canvas/theme context.

## Authoring sequence

1. Identify the audience's question, supplied evidence and requested scope. Preserve sources and qualifications. For academic talks, first read [academic authoring](academic-authoring.md); do not convert every reading-note heading into a slide.
2. Prepare project-local figures using supplied files or dedicated tools. Keep labels, units and uncertainty visible. Native chart/table DSL is an optional structured compatibility path; images do not become editable data charts.
3. Write settings and one candidate using [the starter](authoring-start.md). Create the project with `deck create PROJECT --settings FILE --content FILE`.
4. Use [work objects](review-cli.md) to review and revise the returned page. Record its purpose, claim, evidence and connections with `deck outline`. Open actual preview images; paths and matrix counts are not image review.
5. Insert or split/merge nearby pages as readable typography and figures require. Keep the outline provisional; refine the affected reasoning rather than redesigning the whole deck after every edit.
6. Export and inspect the integrated PPTX with [operations](operations.md), then perform [delivery checks](delivery-checks.md).

Formal YAML is written by the CLI and carries a reminder to modify it through the CLI. Edit a candidate file and pass it to `page update`; do not edit work metadata. On geometry failure, preserve content and correct layout under the returned restrictions.

## Representation boundaries

YAML/JSON encode the schema. Rich text accepts the supported HTML subset. Equations use the routes in [equations](equations.md). TypeScript-shaped schema examples and style Markdown are reference descriptions, not executable source files. Consult [the schema](presentation-schema.md) by field.

Local images must remain inside the project. Copy a shared asset before changing it for only one page. A clearly labeled placeholder is preferable to invented evidence. Fonts must be available to the target viewer; the exporter does not embed them.

Source edits produce local previews, not an updated existing full-deck PPTX. Export for a new integrated artifact, or use [binary page replacement](page-edit.md) to preserve the other slides of an existing file. Review that final artifact independently of the source preview.
