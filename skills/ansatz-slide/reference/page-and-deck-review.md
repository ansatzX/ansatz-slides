# Review the page, then its role in the deck

Use [the page-local API](review-cli.md) to expand and edit one page at a time.
Its output bounds the working context; the model performs the analysis. Use this procedure while authoring and when a requested edit changes content or
layout. For a local edit, keep accepted pages stable. These are author/reviewer
operations supported by focused inputs and single-page writes, not capabilities
of `validate` or `inspect` and not user approval
steps. The CLI checks source/package properties; it does not understand an
argument, image content, visual hierarchy or audience comprehension.

## The page has two separate questions

**Logic:** what can the audience conclude from the evidence actually visible
here, given what earlier pages established? Read the displayed claim, locate its
support, and explain the inference. Check conditions and the meaning of symbols.
A correct caption on the wrong figure panel fails. A legible equation without
its physical correspondence may also fail. Do not use the reading report to
silently supply information that the audience cannot access.

**Spatial explanation:** does the actual rendered page direct the eye through
that reasoning? Inspect the complete page first, then its important regions at
readable resolution. Review the rendered PPTX, not just the YAML coordinates.

- Identify the dominant object and the likely reading order. Does the evidence
  get enough space relative to the title, commentary and decorative containers?
- Trace relationships: which label belongs to which curve, which arrow starts
  and ends on which object, and which equation term names which component?
  Proximity, alignment, color and connectors should support the intended grouping.
- Read each text block through its last line. Inspect all four edges of a plot,
  including ticks, axis labels, legend and qualifiers. A crop can fit perfectly
  inside a slide while cutting away scientific meaning.
- Judge type, contrast, spacing and visual competition at whole-slide scale;
  zooming in until tiny labels become legible does not establish presentation
  readability. Use detail views to diagnose glyphs or clipping, not to excuse
  them. Move or recompose content before squeezing it into a smaller font.
- Check geometry against the source only after seeing the defect: bounds help
  locate an object but do not measure font substitution, text overflow or the
  contents of an image. Blank space can separate ideas; filling every gap is
  not a layout goal. Intentional overlap is not automatically an error.

Use two deliberately different readings: explain the page's reasoning, then
follow its visual attention and relationships. Do not infer either result from
the author's statement that the page was checked. For math assets follow
[equations](equations.md); for unfamiliar academic language check the term's
meaning in context, not a dictionary's first translation.

## Make one correction observable

Keep a short record of a real defect: page/version, visible region or element,
what is wrong, the smallest effective correction, and what the new render shows.
For example: “p6, right plot: y-axis label cut off; enlarge source crop margin;
re-exported label and tick values now readable.” “Axes checked” is not evidence.
No mandatory score, per-element form or extra approval is needed.

Change the rejected page and its dedicated assets. Re-render that page and
check both its reasoning and spatial explanation. When the correction works,
keep it; do not restart global design to chase arbitrary polish. If the source
itself is inconsistent, preserve and qualify it rather than silently repairing
scientific content. An unresolved defect remains unresolved in the handoff.

## The deck asks a different question

Before layout, read the proposed sequence as an argument. After integration,
read the actual titles and pages in order. Identify what each page establishes
and why the next page can use it. Look for missing premises, repeated claims,
changed definitions, mismatched conditions and conclusions stronger than the
presented evidence. Several individually good pages can still form a poor talk.

A contact sheet helps assess rhythm, repeated visual weight and sudden density
changes. It cannot establish detailed typography or figure-label completeness.
Conversely, inspecting pages separately cannot establish the sequence's logic.
Check the ending against the original audience question and the evidence the
deck actually supplied, not the amount of material covered.

For a localized edit, recheck the page's incoming/outgoing reasoning and expand
only to pages that depend on a changed premise or shared asset. For a new deck,
review the whole sequence after its pages are integrated. A single-page preview
reduces review load; the final merged file still needs the checks in
[page editing](page-edit.md).

## Keep the evidence attached to the delivered version

Record the output file/version, actual renderer and which pages were viewed.
After an export changes the file, earlier screenshots are evidence for the old
version until affected pages are re-rendered. Shared font/theme/asset changes can
invalidate more pages. Separate structural checks, page logic, page appearance
and deck coherence; none is a proxy for the others. Automated geometry warnings
or a review checklist may help locate work but cannot issue a content/visual GO.
